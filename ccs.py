import socket
from datetime import datetime


class UdpConnection:
    def __init__(self, socket_obj, host, port):
        self.socket = socket_obj
        self.host = host    
        self.port = port

class BaseCCS:
    # shared command constants
    CMD_STATUS = 0xA0
    CMD_RUN_BOOTLOADER = 0xA1
    CMD_START_FLASHING = 0xA2
    CMD_FLASHING = 0xA3
    CMD_VERIFY_DATA = 0xA4
    CMD_RUN_APP = 0xA5

    BOOTFOTA_FW_RUNNING = 0x11
    APPLICATION_FW_RUNNING = 0x22

    MASTER_CHUTE_CIRCUIT = 0x01
    SLAVE_CHUTE_CIRCUIT = 0x02

    SUCCESS = 0x59
    FAIL = 0x4E

    def __init__(self, host: str, port: int, timeout: float = 1.0, sock: socket.socket = None):
        self.host = host
        self.port = port
        if sock is None:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        else:
            s = sock
        s.settimeout(timeout)
        self.udp = UdpConnection(s, host, port)

    def crc8(self, data: bytes, length: int) -> int:
        crc = 0
        for i in range(length - 1):
            crc ^= data[i]
            for _ in range(8):
                crc = (crc << 1) ^ 0x07 if (crc & 0x80) else (crc << 1)
                crc &= 0xFF
        return crc

    def sendto(self, data_send: bytearray):
        self.udp.socket.sendto(data_send, (self.udp.host, self.udp.port))

    # Backwards-compatible aliases used in original code
    def sendto_master(self, data_send: bytearray):
        """Alias kept for backward compatibility with older function names."""
        return self.sendto(data_send)

    def sendto_slave(self, data_send: bytearray):
        """Alias kept for backward compatibility with older function names."""
        return self.sendto(data_send)

    def build_start_mess_bootFota_process(self, Identify: int, addr_start, addr_end) -> bytearray:
        mess_start_boot = bytearray(12)
        mess_start_boot[0] = Identify & 0x0F
        mess_start_boot[1] = 12
        mess_start_boot[2] = self.CMD_START_FLASHING
        mess_start_boot[3] = (addr_start >> 24) & 0xFF
        mess_start_boot[4] = (addr_start >> 16) & 0xFF
        mess_start_boot[5] = (addr_start >> 8) & 0xFF
        mess_start_boot[6] = (addr_start) & 0xFF
        mess_start_boot[7] = (addr_end >> 24) & 0xFF
        mess_start_boot[8] = (addr_end >> 16) & 0xFF
        mess_start_boot[9] = (addr_end >> 8) & 0xFF
        mess_start_boot[10] = (addr_end) & 0xFF
        mess_start_boot[11] = self.crc8(mess_start_boot, mess_start_boot[1])
        return mess_start_boot

    def build_runApp_fw_mess(self, Identify, stack_pointer, version, _date_now: datetime, type_circuit) -> bytearray:
        mess_run_app = bytearray(14)
        mess_run_app[0] = Identify & 0x0F
        mess_run_app[1] = 14
        mess_run_app[2] = self.CMD_RUN_APP
        mess_run_app[3] = (stack_pointer >> 24) & 0xFF
        mess_run_app[4] = (stack_pointer >> 16) & 0xFF
        mess_run_app[5] = (stack_pointer >> 8) & 0xFF
        mess_run_app[6] = (stack_pointer >> 0) & 0xFF
        mess_run_app[7] = version & 0xFF
        mess_run_app[8] = _date_now.day & 0xFF
        mess_run_app[9] = _date_now.month & 0xFF
        mess_run_app[10] = (_date_now.year >> 8) & 0xFF
        mess_run_app[11] = _date_now.year & 0xFF
        mess_run_app[12] = type_circuit
        mess_run_app[mess_run_app[1] - 1] = self.crc8(mess_run_app, mess_run_app[1])
        return mess_run_app
