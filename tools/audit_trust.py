"""Offline db/dbx and PE digest precheck. Does NOT simulate full UEFI trust policy."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import struct
import uuid

SHA256 = "c1c41626-504c-4092-aca9-41f936934328"
X509 = "a5c059a1-94e4-4aa7-87b5-ab155c2bf072"
X509_SHA256 = "3bd2a492-96c0-4079-b420-fcf98ef103ed"


def esl(data):
    result, pos = [], 0
    while pos < len(data):
        if len(data)-pos < 28:
            raise ValueError("Truncated EFI_SIGNATURE_LIST")
        kind = str(uuid.UUID(bytes_le=data[pos:pos+16]))
        size, header, signature = struct.unpack_from("<III",data,pos+16)
        if size < 28 or size > len(data)-pos or signature < 16 or header > size-28:
            raise ValueError("Invalid EFI_SIGNATURE_LIST sizes")
        start, end = pos+28+header, pos+size
        if (end-start) % signature:
            raise ValueError("Partial signature entry")
        for offset in range(start,end,signature):
            result.append({"type":kind,"owner":str(uuid.UUID(bytes_le=data[offset:offset+16])),
                           "data":data[offset+16:offset+signature]})
        pos = end
    return result


def der_one(data, start=0):
    if start+2>len(data):
        raise ValueError("Truncated DER")
    tag, length = data[start], data[start+1]
    at = start+2
    if length & 128:
        count = length & 127
        if not 1 <= count <= 4 or at+count>len(data):
            raise ValueError("Unsupported DER length")
        length = int.from_bytes(data[at:at+count],"big")
        at += count
    end = at+length
    if end>len(data):
        raise ValueError("DER extends beyond input")
    return {"tag":tag,"value":data[at:end],"raw":data[start:end]},end


def children(node):
    data, pos, nodes = node["value"], 0, []
    while pos < len(data):
        child,pos = der_one(data,pos)
        nodes.append(child)
    return nodes


def pkcs7_details(blob):
    content = children(der_one(blob)[0])
    if content[0]["value"] != bytes.fromhex("2a864886f70d010702"):
        raise ValueError("Expected PKCS7 SignedData")
    signed = children(children(content[1])[0])
    embedded = children(signed[2])
    if embedded[0]["value"] != bytes.fromhex("2b060104018237020104"):
        raise ValueError("Expected SpcIndirectDataContent")
    indirect = children(children(embedded[1])[0])
    digest = children(indirect[1])
    if children(digest[0])[0]["value"] != bytes.fromhex("608648016503040201") or digest[1]["tag"] != 4 or len(digest[1]["value"])!=32:
        raise ValueError("Expected SHA256 Authenticode digest")
    certs = []
    for item in signed[3:]:
        if item["tag"]==0xa0:
            certs.extend(x["raw"] for x in children(item) if x["tag"]==0x30)
    return digest[1]["value"],certs


def pe_hash(data):
    if len(data)<64 or data[:2]!=b"MZ":
        raise ValueError("Not a DOS/PE image")
    pe = struct.unpack_from("<I",data,0x3c)[0]
    if pe+24>len(data) or data[pe:pe+4]!=b"PE\0\0":
        raise ValueError("Invalid PE header")
    count = struct.unpack_from("<H",data,pe+6)[0]
    optsize = struct.unpack_from("<H",data,pe+20)[0]
    opt = pe+24
    if opt+optsize+40*count>len(data) or struct.unpack_from("<H",data,opt)[0]!=0x20b or optsize<152:
        raise ValueError("Expected bounded PE32+ header")
    headers = struct.unpack_from("<I",data,opt+60)[0]
    checksum, security = opt+64, opt+112+4*8
    cert_at, cert_size = struct.unpack_from("<II",data,security)
    if not security+8<=headers<=len(data):
        raise ValueError("Invalid PE headers size")
    h = hashlib.sha256()
    h.update(data[:checksum]); h.update(data[checksum+4:security]); h.update(data[security+8:headers])
    sections = []
    for i in range(count):
        size, offset = struct.unpack_from("<II",data,opt+optsize+40*i+16)
        if size:
            sections.append((offset,size))
    cursor = headers
    for offset,size in sorted(sections):
        # Refuse noncanonical layouts instead of guessing at gaps/overlaps.
        if offset != cursor or size>len(data)-offset:
            raise ValueError("Noncontiguous or overlapping PE raw sections")
        h.update(data[offset:offset+size]); cursor += size
    if cert_size:
        if cert_at<cursor or cert_at+cert_size!=len(data):
            raise ValueError("Unsupported PE certificate-table placement")
        h.update(data[cursor:cert_at])
    else:
        if cert_at:
            raise ValueError("Certificate offset without certificate size")
        if cursor<len(data):
            h.update(data[cursor:])
            h.update(bytes((-len(data))%8))
    return h.digest(), cert_at, cert_size


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collection",type=Path)
    parser.add_argument("--image",type=Path,default=Path("build/shim/shimx64.efi"))
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    stores = {}
    report = {"scope":"Offline precheck only; not a complete signature, timestamp, SBAT or firmware-policy verifier",
              "firmware_boot_tested":False,"stores":{}}
    for name in ("PK","KEK","db","dbx"):
        raw = (args.collection/(name+".bin")).read_bytes()
        entries = esl(raw); stores[name] = entries
        certs = []
        for i,entry in enumerate(entries):
            if entry["type"]==X509:
                path = args.output/f"{name}-{i:03d}.cer"
                path.write_bytes(entry["data"])
                certs.append({"file":path.name,"sha256":hashlib.sha256(entry["data"]).hexdigest()})
        report["stores"][name] = {"bytes":len(raw),"entries":len(entries),
                                   "types":dict(collections.Counter(e["type"] for e in entries)),"certificates":certs}
    data = args.image.read_bytes()
    digest, cert_at, cert_size = pe_hash(data)
    certificates, signed_digests = [], []
    pos = cert_at
    while cert_size and pos < cert_at+cert_size:
        size, rev, kind = struct.unpack_from("<IHH",data,pos)
        if size<8 or pos+size>cert_at+cert_size or rev!=0x200 or kind!=2:
            raise ValueError("Unsupported WIN_CERTIFICATE")
        signed_digest,certs = pkcs7_details(data[pos+8:pos+size])
        signed_digests.append(signed_digest.hex()); certificates.extend(certs)
        pos += (size+7)&~7
    if signed_digests and any(x!=digest.hex() for x in signed_digests):
        raise ValueError("PE hash differs from Authenticode signed-content digest")
    dbx_hashes = {e["data"] for e in stores["dbx"] if e["type"]==SHA256}
    dbx_certs = {e["data"] for e in stores["dbx"] if e["type"]==X509}
    dbx_tbs = {e["data"][:32] for e in stores["dbx"] if e["type"]==X509_SHA256 and len(e["data"])>=32}
    matches = []
    for i,cert in enumerate(certificates):
        (args.output/f"image-cert-{i:03d}.cer").write_bytes(cert)
        tbs = children(der_one(cert)[0])[0]["raw"]
        if cert in dbx_certs: matches.append({"certificate":i,"type":"exact-X509"})
        if hashlib.sha256(tbs).digest() in dbx_tbs:
            matches.append({"certificate":i,"type":"X509-TBS-SHA256; timestamp policy requires further evaluation"})
    known = {SHA256,X509,X509_SHA256}
    report["image"] = {"file":str(args.image),"file_sha256":hashlib.sha256(data).hexdigest(),
                        "authenticode_sha256":digest.hex(),"embedded_digest_matches":bool(signed_digests),
                        "image_hash_in_dbx":digest in dbx_hashes,"embedded_certificate_dbx_matches":matches,
                        "dbx_types_not_evaluated":sorted({e["type"] for e in stores["dbx"]}-known)}
    for name in ("SecureBoot","SetupMode"):
        report[name] = list((args.collection/(name+".bin")).read_bytes())
    (args.output/"audit.json").write_text(json.dumps(report,indent=2))
    print(json.dumps({"SecureBoot":report["SecureBoot"],"SetupMode":report["SetupMode"],
                      "db_entries":report["stores"]["db"]["entries"],"dbx_entries":report["stores"]["dbx"]["entries"],
                      "image":report["image"]},indent=2))


if __name__ == "__main__":
    main()
