import socket
import time
import os
from datetime import datetime
from BootFOTA_Sw_Chute.analysis_hex import analysis_hex
from ccs import BaseCCS, UdpConnection


class Slave(BaseCCS):
    def __init__(self, host: str, port: int, timeout: float = 1.0, sock: socket.socket = None):
        super().__init__(host, port, timeout, sock)
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

    # crc8, send and build_start/build_run_app are inherited from BaseCCS

    def build_forward_mode(self, ID_master: int) -> bytearray:
        data_fwd = bytearray(4)
        data_fwd[0] = 0xD0 | (ID_master & 0x0F)
        data_fwd[1] = 4
        data_fwd[2] = 0x0D
        data_fwd[3] = self.crc8(data_fwd, 4)
        return data_fwd

    def receive_runFWD_mode_master(self, ID_master: int) -> bool:
        try:
            data_read, _ = self.udp.socket.recvfrom(256)
            if len(data_read) > 2:
                cmd = data_read[0] & 0xF0
                id_m = data_read[0] & 0x0F
            else:
                return False

            if self.crc8(data_read, len(data_read)) == data_read[-1] and id_m == ID_master and cmd == 0xD0 and data_read[0] != 0x00:
                print("-> [Received] - ", " ".join(f"{b:02X}" for b in data_read))
                return True
            else:
                return False
        except socket.timeout:
            print("-> [Timeout] - Timeout Receive Response !")
            return False

    def build_request_status_slave(self, ID_master: int, ID_slave: int) -> bytearray:
        data_slave = bytearray(4)
        data_slave[0] = ID_slave
        data_slave[1] = 0x04
        data_slave[2] = self.CMD_STATUS
        data_slave[3] = self.crc8(data_slave, 4)

        data_master = bytearray(7)
        data_master[0] = 0xE0 | (ID_master & 0x0F)
        data_master[1] = 7
        for i in range(0, 4):
            data_master[i + 2] = data_slave[i]
        data_master[6] = self.crc8(data_master, 7)
        return data_master

    def receive_status_slave(self, ID_master: int, ID_slave: int):
        try:
            data_read, _ = self.udp.socket.recvfrom(256)
            if len(data_read) > 3:
                cmd_m = data_read[0] & 0xF0
                id_m = data_read[0] & 0x0F
                id_sl = data_read[2]
                cmd_sl = data_read[4]
            else:
                print("-> [Error] - Response too short !")
                return False, False

            if self.crc8(data_read, len(data_read)) == data_read[-1] and id_m == ID_master and cmd_m == 0xE0 and data_read[0] != 0x00 and id_sl == ID_slave:
                print("-> [Received] - ", " ".join(f"{b:02X}" for b in data_read))
                current_mode = data_read[5]
                ver_app = data_read[6]
                day = data_read[7]
                mon = data_read[8]
                year = (data_read[9] << 8) | data_read[10]
                stack_ptr = (data_read[11] << 24) | (data_read[12] << 16) | (data_read[13] << 8) | data_read[14]
                type_circuit = data_read[15]
                if current_mode == self.BOOTFOTA_FW_RUNNING:
                    mode = "Running Boot FOTA Program"
                elif current_mode == self.APPLICATION_FW_RUNNING:
                    mode = "Running Application Program"
                else:
                    mode = "not found"
                type_ = "not found"
                if type_circuit == self.MASTER_CHUTE_CIRCUIT:
                    type_ = "Master Chute"
                elif type_circuit == self.SLAVE_CHUTE_CIRCUIT:
                    type_ = "Slave Chute"
                print(f"-> [Information]  - Type of circuit: {type_} - ")
                print(f"                  - Identify: {id_m}  ")
                print(f"                  - Current Mode: {mode}  ")
                print(f"                  - Version: {round(ver_app/10,1)} ")
                print(f"                  - Updated on: {day}/{mon}/{year}  ")
                print(f"                  - StackPointer Address: {hex(stack_ptr)}")
                return current_mode, True
            else:
                print("-> [Error] - Unexpected Response !")
                print("-> [Received] - ", " ".join(f"{b:02X}" for b in data_read))
                return False, False
        except socket.timeout:
            print("-> [Timeout] - Timeout Receive Response !")
            return False, False

    def build_start_mess_bootFota_process_slave(self, ID_master: int, Identify: int, addr_start, addr_end) -> bytearray:
        mess_slave = self.build_start_mess_bootFota_process(Identify, addr_start, addr_end)
        mess_sent = bytearray(15)
        mess_sent[0] = 0xE0 | (ID_master & 0x0F)
        mess_sent[1] = 15
        for i in range(len(mess_slave)):
            mess_sent[i + 2] = mess_slave[i]
        mess_sent[14] = self.crc8(mess_sent, 15)
        return mess_sent

    # helper used above: build_start_mess_bootFota_process (same format as master)
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

    def receive_startBootFota_response_slave(self, ID_master: int, SQ_slave: int) -> bool:
        try:
            data_read, _ = self.udp.socket.recvfrom(256)
            if len(data_read) == 9:
                id_m = data_read[0] & 0x0F
                id_s = data_read[2]
                cmd = data_read[4]
                if self.crc8(data_read, len(data_read)) == data_read[-1] and cmd == self.CMD_START_FLASHING and id_m == ID_master and id_s == SQ_slave:
                    print("-> [Received] - ", " ".join(f"{b:02X}" for b in data_read))
                    rlt = data_read[5]
                    num_page = data_read[6]
                    if rlt == self.SUCCESS:
                        print(f"-> [Result] - Erased {num_page} pages on Slave {id_s}, Master {id_m}. Start Flashing Success!")
                        return True
                    else:
                        print("-> [Result] - Erased Fail. Start Flashing Fail !")
                        return False
                else:
                    print("-> [Error] - Unexpected Response!")
                    return False
            else:
                print("-> [Error] - Response too short !")
                return False
        except socket.timeout:
            print("-> [Timeout] - Receive Response Timeout !")
            return False

    def build_runApp_fw_mess_slave(self, ID_master, Identify, stack_pointer, version, _date_now, type_circuit) -> bytearray:
        mess_slave = self.build_runApp_fw_mess(Identify, stack_pointer, version, _date_now, type_circuit)
        mess_sent = bytearray(17)
        mess_sent[0] = 0xE0 | (ID_master & 0x0F)
        mess_sent[1] = 17
        for i in range(len(mess_slave)):
            mess_sent[i + 2] = mess_slave[i]
        mess_sent[16] = self.crc8(mess_sent, 17)
        return mess_sent

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

    def receive_runApp_fw_mess_slave(self, ID_master, SQ_slave):
        try:
            data_read, _ = self.udp.socket.recvfrom(256)
            if len(data_read) == 8:
                id_m = data_read[0] & 0x0F
                id_s = data_read[2]
                cmd = data_read[4]
                if self.crc8(data_read, len(data_read)) == data_read[-1] and id_s == SQ_slave and id_m == ID_master and cmd == self.CMD_RUN_APP:
                    print("-> [Received] - ", " ".join(f"{b:02X}" for b in data_read))
                    rlt = data_read[5]
                    return rlt == self.SUCCESS
                else:
                    print("-> [Error] - Unexpected response!")
                    return False
            else:
                print("-> [Error] - Response too short !")
                return False
        except socket.timeout:
            print("-> Timeout Response !")
            return False

    def build_mess_run_bootFOTA_slave(self, ID_master: int, ID_slave: int) -> bytearray:
        data_slave = bytearray(4)
        data_slave[0] = ID_slave
        data_slave[1] = 0x04
        data_slave[2] = self.CMD_RUN_BOOTLOADER
        data_slave[3] = self.crc8(data_slave, 4)
        data_master = bytearray(7)
        data_master[0] = 0xE0 | (ID_master & 0x0F)
        data_master[1] = 7
        for i in range(0, 4):
            data_master[i + 2] = data_slave[i]
        data_master[6] = self.crc8(data_master, 7)
        return data_master

    def receive_runFOTA_slave_response(self, ID_master: int, SQ_slave: int) -> bool:
        try:
            data_read, _ = self.udp.socket.recvfrom(256)
            if len(data_read) == 8:
                id_m = data_read[0] & 0x0F
                id_s = data_read[2]
                cmd = data_read[4]
                if self.crc8(data_read, len(data_read)) == data_read[-1] and cmd == self.CMD_RUN_BOOTLOADER and id_m == ID_master and id_s == SQ_slave:
                    print("-> [Received] - ", " ".join(f"{b:02X}" for b in data_read))
                    rlt = data_read[5]
                    return rlt == self.SUCCESS
                else:
                    print("-> [Error] - Unexpected Response!")
                    return False
            else:
                print("-> [Error] - Response too short !")
                return False
        except socket.timeout:
            print("-> [Timeout] - Receive Response Timeout !")
            return False

    # High-level sequences
    def run_FWD_master(self, ID_master: int, retry: int = 3) -> bool:
        print(f"\n>>>>>>>>>>>>>> RUN FORWADER MODE MASTER {ID_master}, HOST '{self.udp.host}', PORT '{self.udp.port}'\n")
        mess_sent = self.build_forward_mode(ID_master)
        while retry > 0:
            self.sendto_master(mess_sent)
            print("-> [Sent] - ", " ".join(f"{b:02X}" for b in mess_sent))
            result = self.receive_runFWD_mode_master(ID_master)
            if result:
                print(f"-> [Result] - Run forwarder mode on MASTER {ID_master} Success !")
                return True
            else:
                retry -= 1
            time.sleep(0.5)
        print(f"-> [Result] - Run forwarder mode on MASTER {ID_master} Fail !")
        return False

    def request_status_slave(self, ID_master: int, ID_slave: int, retry: int = 3):
        print(f"\n>>>>>>>>>>>>>> REQUEST STATUS SLAVE {ID_slave}, MASTER {ID_master}, HOST '{self.udp.host}', PORT '{self.udp.port}'\n")
        mess_sent = self.build_request_status_slave(ID_master, ID_slave)
        while retry > 0:
            self.sendto_master(mess_sent)
            print("-> [Sent] - ", " ".join(f"{b:02X}" for b in mess_sent))
            current_mode, result = self.receive_status_slave(ID_master, ID_slave)
            if result:
                return current_mode
            else:
                retry -= 1
            time.sleep(0.5)
        print(f"-> [Result] - Request Status SLAVE {ID_slave}, MASTER {ID_master} Fail !")
        return False

    def start_bootFota_process(self, ID_master: int, SQ_slave: int, addr_start=0, addr_end=0, retry: int = 3) -> bool:
        print(f"\n>>>>>>>>>>>>>> START BOOT FOTA PROCESS ON SLAVE {SQ_slave}, MASTER {ID_master}, HOST '{self.udp.host}', PORT '{self.udp.port}'\n")
        mess_sent = self.build_start_mess_bootFota_process_slave(ID_master, SQ_slave, addr_start, addr_end)
        while retry > 0:
            self.sendto_master(mess_sent)
            print("-> [Sent] - ", " ".join(f"{b:02X}" for b in mess_sent))
            time.sleep(0.001)
            result = self.receive_startBootFota_response_slave(ID_master, SQ_slave)
            if result:
                print(f"-> [Result] - Start Flashing from {hex(addr_start)} to {hex(addr_end)} on SLAVE {SQ_slave} MASTER {ID_master} !")
                return True
            else:
                retry -= 1
            time.sleep(0.5)
        print(f"-> [Result] - Start Flashing Process on MASTER {ID_master} Fail !")
        return False

    def flashing_slave_process(self, ID_master: int, SQ_slave: int, _list_hex_data: list, retry: int = 3) -> bool:
        print(f"\n>>>>>>>>>>>>>> FLASHING  PROCESS ON SLAVE {SQ_slave}, MASTER {ID_master}, HOST '{self.udp.host}', PORT '{self.udp.port}'\n")
        cnt_line_data = 0
        cnt_error = 0
        start_flash_t = time.time()
        while cnt_line_data < len(_list_hex_data):
            entry = _list_hex_data[cnt_line_data]
            data_bytes = entry.get('data', b'')
            lenData = len(data_bytes)
            mess_flash_data = bytearray(lenData + 8)
            mess_flash_data[0] = SQ_slave & 0x0F
            mess_flash_data[1] = lenData + 8
            mess_flash_data[2] = self.CMD_FLASHING
            addr = entry.get('address', 0)
            mess_flash_data[3] = (addr >> 24) & 0xFF
            mess_flash_data[4] = (addr >> 16) & 0xFF
            mess_flash_data[5] = (addr >> 8) & 0xFF
            mess_flash_data[6] = (addr) & 0xFF
            for j in range(0, lenData):
                mess_flash_data[j + 7] = data_bytes[j]
            mess_flash_data[mess_flash_data[1] - 1] = self.crc8(mess_flash_data, mess_flash_data[1])

            mess_sent = bytearray(len(mess_flash_data) + 3)
            mess_sent[0] = 0xE0 | (ID_master & 0x0F)
            mess_sent[1] = len(mess_flash_data) + 3
            for i in range(len(mess_flash_data)):
                mess_sent[i + 2] = mess_flash_data[i]
            mess_sent[len(mess_flash_data) + 2] = self.crc8(mess_sent, len(mess_sent))

            self.sendto_master(mess_sent)
            time.sleep(0.01)
            try:
                data_read, _ = self.udp.socket.recvfrom(256)
                if len(data_read) == 9:
                    id_m = data_read[0] & 0x0F
                    id_s = data_read[2]
                    cmd = data_read[4]
                    if self.crc8(data_read, len(data_read)) == data_read[-1] and id_m == ID_master and cmd == self.CMD_FLASHING and id_s == SQ_slave:
                        rlt = data_read[5]
                        num_byte = data_read[6]
                        if rlt == self.SUCCESS:
                            print(f"-> [Result] - Flashing {num_byte} bytes Success")
                            cnt_line_data += 1
                        else:
                            print(f"-> [Result] - Flashing {num_byte} bytes Fail !")
                            cnt_error += 1
                    else:
                        print("-> [Error] - Unexpected response !")
                        cnt_error += 1
                else:
                    print("-> [Error] - Response too short !")
            except socket.timeout:
                print("-> [Timeout] - Receive Response Timeout !")
                cnt_error += 1

            if cnt_error >= retry:
                print("\n-> [Error] - Flashing BROKEN and FAIL!\n")
                return False
            time.sleep(0.001)

        print(f"\n-> FINISH FLASHING SUCCESS ({round(time.time() - start_flash_t, 3)}s) !\n")
        return True

    def run_Application_fw_slave(self, ID_master: int, SQ_slave: int, stack_pointer: int, version: int, type_circuit: int, retry: int = 3) -> bool:
        print(f"\n>>>>>>>>>>>>>> RUN APPLICATION FIRMWARE ON SLAVE {SQ_slave}, MASTER {ID_master}, HOST '{self.udp.host}', PORT '{self.udp.port}'\n")
        date_now = datetime.now()
        mess_sent = self.build_runApp_fw_mess_slave(ID_master, SQ_slave, stack_pointer, version, date_now, type_circuit)
        while retry > 0:
            self.sendto_master(mess_sent)
            print("-> [Sent] - ", " ".join(f"{b:02X}" for b in mess_sent))
            time.sleep(0.01)
            result = self.receive_runApp_fw_mess_slave(ID_master, SQ_slave)
            if result:
                print(f"-> [Result] - Run New App Firmware on SLAVE {SQ_slave}, MASTER {ID_master}, version {round(version/10,1)}")
                return True
            time.sleep(0.5)
            retry -= 1
        print(f"-> [Result] - Run New App Firmware on SLAVE{SQ_slave}, MASTER {ID_master} Fail !")
        return False

    def run_bootFOTA_Fw_slave(self, ID_master: int, SQ_slave: int, retry: int = 3) -> bool:
        print(f"\n>>>>>>>>>>>>>> RUN BOOT FOTA FIRMWARE ON SLAVE {SQ_slave}, MASTER {ID_master}, HOST '{self.udp.host}', PORT '{self.udp.port}'\n")
        mess_sent = self.build_mess_run_bootFOTA_slave(ID_master, SQ_slave)
        while retry > 0:
            self.sendto_master(mess_sent)
            print("-> [Sent] - ", " ".join(f"{b:02X}" for b in mess_sent))
            time.sleep(0.01)
            result = self.receive_runFOTA_slave_response(ID_master, SQ_slave)
            if result:
                print(f"-> [Result] - Run Boot FOTA SLAVE {SQ_slave} ON MASTER {ID_master} Success !")
                return True
            else:
                retry -= 1
            time.sleep(0.5)
        print(f"-> [Result] - Run Boot FOTA Program on SLAVE {SQ_slave}, MASTER {ID_master} Fail !")
        return False

    def analysisHex_slaveFW(self, type="halfword"):
        print("\n>>>>>>>>>>>>>> ANALYSING HEX FILE   \n")
        path_firmware = input(
            "> Enter the path of SLAVE firmware hex file: ")
        if os.path.isfile(path_firmware) == False:
            print(f"-> [Error] - File {path_firmware} not found !")
            path_firmware = path_firmware
            print(f"-> [INFOR] - Using path: {path_firmware}\n")
        num_Line, list_data_flash, size_Hex, addr_start, addr_end = analysis_hex(path_firmware, type)
        print(f"-> [INFOR FIRMWARE] - [{type}]")
        print(f"->                  - Number Line: {num_Line}")
        print(f"->                  - Address start Flashing: {hex(addr_start)}")
        print(f"->                  - Address end Flashing: {hex(addr_end)}")
        print(f"->                  - Size program: {size_Hex}", " bytes = ", str(round(size_Hex / 1024, 2)) + "kB")
        return list_data_flash, addr_start, addr_end

    def log_to_file(self, log_message: str, filename: str = "result_boot_chute_slave.txt"):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"[{now}] {log_message}\n")
