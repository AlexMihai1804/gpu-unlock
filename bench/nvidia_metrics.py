"""Read NVIDIA telemetry and export the V/F curve; no device setters here."""
import ctypes as ct
import hashlib
import os
from pathlib import Path
import struct
import time


class ClockOffset(ct.Structure):
    _fields_ = [('version', ct.c_uint), ('type', ct.c_int), ('pstate', ct.c_int),
                ('offset', ct.c_int), ('minimum', ct.c_int), ('maximum', ct.c_int)]


class Utilization(ct.Structure):
    _fields_ = [('gpu', ct.c_uint), ('memory', ct.c_uint)]


class ThermalSensor(ct.Structure):
    _fields_ = [('controller', ct.c_int), ('minimum', ct.c_int), ('maximum', ct.c_int),
                ('temperature', ct.c_int), ('target', ct.c_int)]


class ThermalSettings(ct.Structure):
    _fields_ = [('count', ct.c_uint), ('sensor', ThermalSensor * 3)]


class Nvml:
    def __init__(self):
        self.path = Path(os.environ['SystemRoot']) / 'System32/nvml.dll'
        self.lib = ct.WinDLL(str(self.path))
        self.check(self.bind('nvmlInit_v2', [])(), 'nvmlInit')
        self.device = ct.c_void_p()
        try:
            # Pin the physical GPU; never select the first device implicitly.
            self.check(self.bind('nvmlDeviceGetHandleByPciBusId_v2',
                [ct.c_char_p, ct.POINTER(ct.c_void_p)])(b'00000000:01:00.0', ct.byref(self.device)), 'GPU PCI handle')
        except BaseException:
            self.close()
            raise

    def bind(self, name, args):
        fn = getattr(self.lib, name)
        fn.argtypes, fn.restype = args, ct.c_int
        return fn

    def check(self, code, operation):
        if code:
            fn = self.lib.nvmlErrorString
            fn.argtypes, fn.restype = [ct.c_int], ct.c_char_p
            raise RuntimeError(f'{operation}: NVML {code}: {fn(code).decode()}')

    def scalar(self, name, kind=ct.c_uint, args=()):
        result = kind()
        code = self.bind(name, [ct.c_void_p] + [ct.c_uint] * len(args) +
                         [ct.POINTER(kind)])(self.device, *args, ct.byref(result))
        self.check(code, name)
        return result.value

    def offset(self, pstate=0, domain=0):
        value = ClockOffset(ct.sizeof(ClockOffset) | (1 << 24), domain, pstate, 0, 0, 0)
        self.check(self.bind('nvmlDeviceGetClockOffsets', [ct.c_void_p, ct.POINTER(ClockOffset)])(
            self.device, ct.byref(value)), 'read clock offset')
        return {key: getattr(value, key) for key, _ in ClockOffset._fields_}

    def offsets(self):
        # NVIDIA's API can expose offsets globally even when given a pstate.
        return {str(state): self.offset(state) for state in range(16)}

    def energy(self):
        return self.scalar('nvmlDeviceGetTotalEnergyConsumption', ct.c_ulonglong)

    def sample(self):
        util = Utilization()
        self.check(self.bind('nvmlDeviceGetUtilizationRates', [ct.c_void_p, ct.POINTER(Utilization)])(
            self.device, ct.byref(util)), 'utilization')
        return dict(temperature_c=self.scalar('nvmlDeviceGetTemperature', args=(0,)),
            power_w=self.scalar('nvmlDeviceGetPowerUsage') / 1000,
            enforced_limit_w=self.scalar('nvmlDeviceGetEnforcedPowerLimit') / 1000,
            sm_clock_mhz=self.scalar('nvmlDeviceGetClockInfo', args=(1,)),
            memory_clock_mhz=self.scalar('nvmlDeviceGetClockInfo', args=(2,)),
            utilization_percent=util.gpu,
            clocks_event_reasons=self.scalar('nvmlDeviceGetCurrentClocksEventReasons', ct.c_ulonglong))

    def inventory(self):
        sensors = ThermalSettings()
        sensors.count = 3
        rc = self.bind('nvmlDeviceGetThermalSettings',
            [ct.c_void_p, ct.c_uint, ct.POINTER(ThermalSettings)])(self.device, 15, ct.byref(sensors))
        return dict(library=str(self.path), library_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest(),
            energy_counter_mj=self.energy(), graphics_offsets=self.offsets(),
            memory_offset=self.offset(0, 2), thermal_status=rc,
            thermal_sensors=[{key: getattr(s, key) for key, _ in ThermalSensor._fields_}
                for s in sensors.sensor[:min(sensors.count, 3)]] if rc == 0 else [], sample=self.sample())

    def sample_with_retry(self, report_error, attempts=3, delay_seconds=.2):
        """Retry only UNKNOWN telemetry errors; report every failure, never invent data.

        Offset setters/readback and all other NVML errors remain fail-fast.
        A persistent UNKNOWN error still raises after the bounded attempts.
        """
        if not 1 <= attempts <= 3 or not 0 <= delay_seconds <= .5:
            raise ValueError('Telemetry retries must be bounded')
        for attempt in range(1, attempts + 1):
            try:
                return self.sample()
            except RuntimeError as error:
                if 'NVML 999:' not in str(error):
                    raise
                report_error(dict(error=str(error), attempt=attempt,
                                  retrying=attempt < attempts))
                if attempt == attempts:
                    raise
                time.sleep(delay_seconds)

    def close(self):
        self.check(self.bind('nvmlShutdown', [])(), 'nvmlShutdown')


class Nvapi:
    # Only read-only entry points. V/F layout is private: archive raw bytes too.
    def __init__(self):
        self.path = Path(os.environ['SystemRoot']) / 'System32/nvapi64.dll'
        self.lib = ct.WinDLL(str(self.path))
        self.query = self.lib.nvapi_QueryInterface
        self.query.argtypes, self.query.restype = [ct.c_uint], ct.c_void_p
        self.check(self.function(0x0150E828, [])(), 'initialize')
        handles, count = (ct.c_void_p * 64)(), ct.c_uint()
        self.check(self.function(0xE5AC921F, [ct.c_void_p, ct.POINTER(ct.c_uint)])(
            handles, ct.byref(count)), 'enumerate')
        selected = []
        for handle in handles[:count.value]:
            bus = ct.c_uint()
            self.check(self.function(0x1BE0B8E5, [ct.c_void_p, ct.POINTER(ct.c_uint)])(
                handle, ct.byref(bus)), 'bus ID')
            if bus.value == 1:
                selected.append(handle)
        if len(selected) != 1:
            raise RuntimeError('NVAPI GPU bus 1 is ambiguous or missing')
        self.device = selected[0]
        self.voltage_fn = self.function(0x465F9BCF, [ct.c_void_p, ct.c_void_p])

    def function(self, identifier, args):
        address = self.query(identifier)
        if not address:
            raise RuntimeError(f'NVAPI entry {identifier:#x} unavailable')
        return ct.CFUNCTYPE(ct.c_int, *args)(address)

    @staticmethod
    def check(code, operation):
        if code:
            raise RuntimeError(f'NVAPI {operation}: {code}')

    def voltage(self):
        raw = ct.create_string_buffer(76)
        struct.pack_into('<I', raw, 0, 76 | (1 << 16))
        self.check(self.voltage_fn(self.device, raw), 'voltage')
        mv = struct.unpack_from('<I', raw, 40)[0] / 1000
        return mv if 300 <= mv <= 1500 else None

    def curve(self, path):
        raw = ct.create_string_buffer(7208)
        struct.pack_into('<I4I', raw, 0, 7208 | (1 << 16), *([0xffffffff] * 4))
        self.check(self.function(0x21537AD4, [ct.c_void_p, ct.c_void_p])(self.device, raw), 'V/F curve')
        path.write_bytes(raw.raw)
        points = []
        for index in range(80):
            frequency, voltage = struct.unpack_from('<II', raw, 0x48 + index * 28)
            if not frequency and not voltage:
                continue
            if not (100_000 <= frequency <= 3_000_000 and 300_000 <= voltage <= 1_500_000):
                raise RuntimeError('V/F curve layout failed range validation')
            points.append(dict(index=index, frequency_mhz=frequency / 1000, voltage_mv=voltage / 1000))
        if len(points) < 20 or any(b['voltage_mv'] <= a['voltage_mv'] for a, b in zip(points, points[1:])):
            raise RuntimeError('V/F curve failed ordering validation')
        return dict(private_read_only_interface=True, raw_sha256=hashlib.sha256(raw.raw).hexdigest(),
            captured_gpu_points=len(points), complete_curve_guaranteed=False, points=points,
            layout_source='https://github.com/falahati/NvAPIWrapper/blob/2a41eb4d6b1bceff5dbb33a3b5ea70bd582214a7/NvAPIWrapper/Native/GPU/Structures/PrivateVFPCurveV1.cs')

    def close(self):
        self.check(self.function(0xD22BDD7E, [])(), 'unload')
