import socket
import time
import os
from datetime import datetime
from BootFOTA_Sw_Chute.analysis_hex import analysis_hex
from ccs import BaseCCS, UdpConnection


class Master(BaseCCS):
    def __init__(self, host: str, port: int, timeout: float = 1.0, sock: socket.socket = None):
        super().__init__(host, port, timeout, sock)

    # Builders specific to Master
    def build_mess_reset_master(self, ID_master: int) -> bytearray:
        data_reset = bytearray(4)
        data_reset[0] = 0x60 | (ID_master & 0x0F)
        data_reset[1] = 4
        data_reset[2] = 0x06
        data_reset[3] = self.crc8(data_reset, 4)
        return data_reset

    def build_mess_request_status_master(self, Identify: int) -> bytearray:
        status_mess = bytearray(4)
        status_mess[0] = 0xB0 | (Identify & 0x0F)
        status_mess[1] = 4
        status_mess[2] = 0xA0
        status_mess[3] = self.crc8(status_mess, 4)
        return status_mess

    def build_mess_run_bootFOTA_master(self, Identify: int) -> bytearray:
        runFOTA_mess = bytearray(4)
        runFOTA_mess[0] = 0xC0 | (Identify & 0x0F)
        runFOTA_mess[1] = 4
        runFOTA_mess[2] = 0x0C
        runFOTA_mess[3] = self.crc8(runFOTA_mess, 4)
        return runFOTA_mess

    # Receive / parse helpers. Implemented with reasonable behavior when certain detailed parts are omitted.
    def receive_reset_master_response(self, ID_master):
        try:
            data_read, _ = self.udp.socket.recvfrom(256)
            id_m = data_read[0] & 0x0F
            if self.crc8(data_read, len(data_read)) == data_read[-1] and id_m == ID_master and data_read[0] != 0x00:
                print("-> [Received] - ", " ".join(f"{b:02X}" for b in data_read))
                return True
            else:
                return False
        except socket.timeout:
            print("-> [Timeout] - Timeout Receive Response !")
            return False

    def receive_status_master(self, ID_master):
        try:
            data_read, _ = self.udp.socket.recvfrom(256)
            if len(data_read) > 2:
                id_m = data_read[0] & 0x0F
                cmd = data_read[0] & 0xF0
            else:
                return None, False

            if self.crc8(data_read, len(data_read)) == data_read[-1] and data_read[0] != 0x00 and id_m == ID_master and cmd == 0xB0:
                print("-> [Received] - ", " ".join(f"{b:02X}" for b in data_read))
                current_mode = data_read[3]
                ver_app = data_read[4] if len(data_read) > 4 else 0
                day = data_read[5] if len(data_read) > 5 else 0
                mon = data_read[6] if len(data_read) > 6 else 0
                year = ((data_read[7] << 8) | data_read[8]) if len(data_read) > 8 else 0
                stack_ptr = 0
                if len(data_read) >= 13:
                    stack_ptr = (data_read[9] << 24) | (data_read[10] << 16) | (data_read[11] << 8) | data_read[12]
                type_circuit = data_read[13] if len(data_read) > 13 else 0

                # Provide simple printable info
                if current_mode == self.BOOTFOTA_FW_RUNNING:
                    print("-> [Information] - Current Mode: BOOTFOTA firmware running")
                elif current_mode == self.APPLICATION_FW_RUNNING:
                    print("-> [Information] - Current Mode: APPLICATION firmware running")
                else:
                    print("-> [Information] - Current Mode: Unknown")

                type_ = "not found"
                if type_circuit == self.MASTER_CHUTE_CIRCUIT:
                    type_ = "MASTER"
                elif type_circuit == self.SLAVE_CHUTE_CIRCUIT:
                    type_ = "SLAVE"
                print(f"-> [Information]  - Type of circuit: {type_} - ")

                # Return current_mode so caller can use it
                return current_mode, True
            else:
                return None, False
        except socket.timeout:
            print("-> [Timeout] - Receive Response Timeout !")
            return None, False

    def receive_runFOTA_master_response(self, ID_master):
        try:
            data_read, _ = self.udp.socket.recvfrom(256)
            if len(data_read) > 2:
                id_m = data_read[0] & 0x0F
                cmd = data_read[0] & 0xF0
            else:
                return False

            if self.crc8(data_read, len(data_read)) == data_read[-1] and cmd == 0xC0 and id_m == ID_master and data_read[0] != 0x00:
                print("-> [Received] - ", " ".join(f"{b:02X}" for b in data_read))
                # assume success if payload contains SUCCESS byte somewhere
                if any(b == self.SUCCESS for b in data_read):
                    return True
                else:
                    return False
            else:
                return False
        except socket.timeout:
            print("-> [Timeout] - Receive Response Timeout !")
            return False

    def receive_startBootFota_response(self, ID_master):
        try:
            data_read, _ = self.udp.socket.recvfrom(256)
            if len(data_read) > 2:
                id_m = data_read[0] & 0x0F
                cmd = data_read[2] if len(data_read) > 2 else (data_read[0] & 0xF0)
            else:
                return False

            if self.crc8(data_read, len(data_read)) == data_read[-1] and cmd == self.CMD_START_FLASHING and id_m == ID_master and data_read[0] != 0x00:
                print("-> [Received] - ", " ".join(f"{b:02X}" for b in data_read))
                # success when return contains SUCCESS
                return any(b == self.SUCCESS for b in data_read)
            else:
                return False
        except socket.timeout:
            print("-> [Timeout] - Receive Response Timeout !")
            return False

    def receive_runApp_fw_mess(self, ID_master):
        try:
            data_read, _ = self.udp.socket.recvfrom(256)
            if len(data_read) > 2:
                id_m = data_read[0] & 0x0F
                cmd = data_read[0] & 0xF0
            else:
                return False

            if self.crc8(data_read, len(data_read)) == data_read[-1] and data_read[0] != 0x00 and id_m == ID_master and cmd == self.CMD_RUN_APP:
                print("-> [Received] - ", " ".join(f"{b:02X}" for b in data_read))
                return True
            else:
                return False
        except socket.timeout:
            print("-> Timeout Response !")
            return False

    # High-level sequences (reset, request status, run bootfota, start flash, flashing, run app)
    def reset_master(self, ID_master: int, retry: int = 3) -> bool:
        print(f"\n>>>>>>>>>>>>>> RESET MASTER {ID_master}, HOST '{self.udp.host}', PORT '{self.udp.port}'\n")
        mess_reset = self.build_mess_reset_master(ID_master)
        while retry > 0:
            self.sendto_master(mess_reset)
            print("-> [Sent] - ", " ".join(f"{b:02X}" for b in mess_reset))
            time.sleep(0.01)
            if self.receive_reset_master_response(ID_master):
                print(f"-> [Result] - Reset MASTER {ID_master} OK !")
                return True
            else:
                retry -= 1
                print(f"-> [Retry] - Remaining: {retry}")
            time.sleep(0.5)
        print(f"-> [Result] - Reset MASTER {ID_master} Fail !")
        return False

    def request_status_master(self, ID_master: int, retry: int = 3):
        print(f"\n>>>>>>>>>>>>>> REQUEST STATUS MASTER {ID_master}, HOST '{self.udp.host}', PORT '{self.udp.port}'\n")
        mess_status = self.build_mess_request_status_master(ID_master)
        while retry > 0:
            self.sendto_master(mess_status)
            print("-> [Sent] - ", " ".join(f"{b:02X}" for b in mess_status))
            time.sleep(0.01)
            current_mode, result = self.receive_status_master(ID_master)
            if result:
                return current_mode
            else:
                retry -= 1
                print(f"-> [Retry] - Remaining: {retry}")
            time.sleep(0.5)
        print(f"-> [Result] - Request Status MASTER {ID_master} Fail !")
        return None

    def run_bootFOTA_Fw_master(self, ID_master: int, retry: int = 3) -> bool:
        print(f"\n>>>>>>>>>>>>>> RUN BOOT FOTA FIRMWARE ON MASTER {ID_master}, HOST '{self.udp.host}', PORT '{self.udp.port}'\n")
        mess_fota = self.build_mess_run_bootFOTA_master(ID_master)
        while retry > 0:
            self.sendto_master(mess_fota)
            print("-> [Sent] - ", " ".join(f"{b:02X}" for b in mess_fota))
            time.sleep(0.01)
            if self.receive_runFOTA_master_response(ID_master):
                print("-> [Result] - Run Boot FOTA OK")
                return True
            else:
                retry -= 1
                print(f"-> [Retry] - Remaining: {retry}")
            time.sleep(0.5)
        print(f"-> [Result] - Run Boot FOTA Program on MASTER {ID_master} Fail !")
        return False

    def start_bootFota_process(self, ID_master: int, addr_start=0, addr_end=0, retry: int = 3) -> bool:
        print(f"\n>>>>>>>>>>>>>> START BOOT FOTA PROCESS ON MASTER {ID_master}, HOST '{self.udp.host}, PORT '{self.udp.port}'\n")
        mess_start = self.build_start_mess_bootFota_process(ID_master, addr_start, addr_end)
        while retry > 0:
            self.sendto_master(mess_start)
            print("-> [Sent] - ", " ".join(f"{b:02X}" for b in mess_start))
            time.sleep(0.01)
            if self.receive_startBootFota_response(ID_master):
                print("-> [Result] - Start Boot FOTA OK")
                return True
            else:
                retry -= 1
                print(f"-> [Retry] - Remaining: {retry}")
            time.sleep(0.5)
        print(f"-> [Result] - Start Flashing Process on MASTER {ID_master} Fail !")
        return False

    def flashing_master_process(self, ID_master: int, _list_hex_data: list, retry: int = 3) -> bool:
        print(f"\n>>>>>>>>>>>>>> FLASHING  PROCESS ON MASTER {ID_master}, HOST '{self.udp.host}', PORT '{self.udp.port}'\n")
        cnt_line_data = 0
        cnt_error = 0
        start_flash_t = time.time()
        while cnt_line_data < len(_list_hex_data):
            entry = _list_hex_data[cnt_line_data]
            data_bytes = entry.get('data', b'')
            lenData = len(data_bytes)
            mess_flash_data = bytearray(lenData + 8)
            mess_flash_data[0] = ID_master & 0x0F
            mess_flash_data[1] = lenData + 8
            mess_flash_data[2] = self.CMD_FLASHING
            addr = entry.get('address', 0)
            mess_flash_data[3] = (addr >> 24) & 0xFF
            mess_flash_data[4] = (addr >> 16) & 0xFF
            mess_flash_data[5] = (addr >> 8) & 0xFF
            mess_flash_data[6] = (addr) & 0xFF
            for j in range(0, lenData):
                mess_flash_data[7 + j] = data_bytes[j]
            mess_flash_data[mess_flash_data[1] - 1] = self.crc8(mess_flash_data, mess_flash_data[1])

            # send and wait for acknowledgement
            self.sendto_master(mess_flash_data)
            # print("-> [Sent] - ", " ".join(f"{b:02X}" for b in mess_flash_data))
            time.sleep(0.01)
            try:
                data_read, _ = self.udp.socket.recvfrom(256)
                # simple check: CRC and matching id
                if self.crc8(data_read, len(data_read)) == data_read[-1] and (data_read[0] & 0x0F) == ID_master:
                    cnt_line_data += 1
                    cnt_error = 0
                else:
                    cnt_error += 1
            except socket.timeout:
                cnt_error += 1

            if cnt_error >= retry:
                print(f"-> [Error] - Too many errors for line {cnt_line_data}")
                return False
            time.sleep(0.001)

        print(f"\n-> FINISH FLASHING SUCCESS ({round(time.time() - start_flash_t, 3)}s) !\n")
        return True

    def run_Application_fw_master(self, ID_master: int, stack_pointer: int, version: int, type_circuit: int, retry: int = 3) -> bool:
        print(f"\n>>>>>>>>>>>>>> RUN APPLICATION FIRMWARE ON MASTER {ID_master}, HOST '{self.udp.host}', PORT '{self.udp.port}'\n")
        date_now = datetime.now()
        mess_run_app = self.build_runApp_fw_mess(ID_master, stack_pointer, version, date_now, type_circuit)
        while retry > 0:
            self.sendto_master(mess_run_app)
            print("-> [Sent] - ", " ".join(f"{b:02X}" for b in mess_run_app))
            time.sleep(0.01)
            if self.receive_runApp_fw_mess(ID_master):
                print("-> [Result] - Run Application OK")
                return True
            else:
                retry -= 1
                print(f"-> [Retry] - Remaining: {retry}")
            time.sleep(0.5)
        print(f"-> [Result] - Run New App Firmware on MASTER {ID_master} Fail !")
        return False

    # hex analysis wrapper
    def analysisHex_masterFW(self, type="halfword"):
        print("\n>>>>>>>>>>>>>> ANALYSING HEX FILE   \n")
        path_firmware = input(
            "> Enter the path of MASTER firmware hex file: ")
        if os.path.isfile(path_firmware) == False:
            print(f"-> [Error] - File {path_firmware} not found !")
            path_firmware = path_firmware  # keep user path; caller can change
            print(f"-> [INFOR] - Using path: {path_firmware}\n")

        num_Line, list_data_flash, size_Hex, addr_start, addr_end = analysis_hex(path_firmware, type)
        print(f"-> [INFOR FIRMWARE] - [{type}]")
        print(f"->                  - Number Line: {num_Line}")
        print(f"->                  - Address start Flashing: {hex(addr_start)}")
        print(f"->                  - Address end Flashing: {hex(addr_end)}")
        print(f"->                  - Size program: {size_Hex}", " bytes = ", str(round(size_Hex / 1024, 2)) + "kB")
        return list_data_flash, addr_start, addr_end

    def log_to_file(self, log_message: str, filename: str = "result_boot_chute_master.txt"):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"[{now}] {log_message}\n")
