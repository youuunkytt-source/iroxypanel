import http.server
import json
import threading
import time
import ctypes
import win32api
import win32con
import keyboard
import pydivert
import os

# Глобальные переменные
running = True
tele_mode = False
freeze_mode = False
R_O = False
R_I = False
packet_tele = []
packet_freeze = []
lock = threading.Lock()

FILTER_O = "udp and udp.DstPort >= 10000 and udp.DstPort <= 10099 and ip.Length > 54"
FILTER_I = "inbound and udp.SrcPort >= 10000 and udp.SrcPort <= 10099 and ip and ip.Protocol == 17 and ip.Length >= 50 and ip.Length <= 1491"

def send_packets(lst, f):
    try:
        with pydivert.WinDivert(f, layer=pydivert.Layer.NETWORK) as s:
            for pkt in lst:
                try:
                    s.send(pydivert.Packet(pkt.raw, pkt.interface, pkt.direction))
                except:
                    pass
    except:
        pass

def toggle_tele():
    global tele_mode, R_O, packet_tele
    try:
        if tele_mode:
            with lock:
                tele_mode = False
                R_O = False
                to_send = list(packet_tele)
                packet_tele.clear()
            if to_send:
                threading.Thread(target=send_packets, args=(to_send, FILTER_O), daemon=True).start()
            return False
        else:
            with lock:
                tele_mode = True
                R_O = True
                packet_tele.clear()
            return True
    except:
        return False

def toggle_freeze():
    global freeze_mode, R_I, packet_freeze
    try:
        if freeze_mode:
            freeze_mode = False
            R_I = False
            with lock:
                packets = list(packet_freeze)
                packet_freeze.clear()
            threading.Thread(target=send_packets, args=(packets, FILTER_I), daemon=True).start()
            return False
        else:
            freeze_mode = True
            R_I = True
            return True
    except:
        return False

def divert(filter_str, flag_ref, packet_list, cond_ref):
    h = None
    try:
        while running:
            try:
                if not flag_ref():
                    if h:
                        try:
                            h.close()
                        except:
                            pass
                        h = None
                    time.sleep(0.1)
                    continue
                    
                if h is None:
                    try:
                        h = pydivert.WinDivert(filter_str)
                        h.open()
                    except:
                        h = None
                        time.sleep(1)
                        continue
                        
                try:
                    for pkt in h:
                        if not running or not flag_ref():
                            break
                        with lock:
                            if cond_ref():
                                packet_list.append(pydivert.Packet(pkt.raw, pkt.interface, pkt.direction))
                                continue
                        try:
                            h.send(pkt)
                        except:
                            pass
                except:
                    if h:
                        try:
                            h.close()
                        except:
                            pass
                    h = None
                    time.sleep(0.5)
            except:
                time.sleep(0.5)
    except:
        pass
    finally:
        if h:
            try:
                h.close()
            except:
                pass

class RequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/start_tele':
            result = toggle_tele()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "tele_mode": result}).encode())
            
        elif self.path == '/stop_tele':
            if tele_mode:
                toggle_tele()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "tele_mode": False}).encode())
            
        elif self.path == '/start_freeze':
            result = toggle_freeze()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "freeze_mode": result}).encode())
            
        elif self.path == '/stop_freeze':
            if freeze_mode:
                toggle_freeze()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "freeze_mode": False}).encode())
            
        elif self.path == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "tele_mode": tele_mode,
                "freeze_mode": freeze_mode
            }).encode())
            
        elif self.path == '/shutdown':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "message": "Shutting down"}).encode())
            global running
            running = False
            threading.Thread(target=lambda: os._exit(0), daemon=True).start()
            
        else:
            self.send_response(404)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": "Not found"}).encode())
    
    def log_message(self, format, *args):
        pass  # Отключаем логирование в консоль

def start_server():
    # Запускаем потоки для фильтрации трафика
    threading.Thread(target=divert, args=(FILTER_O, lambda: R_O, packet_tele, lambda: tele_mode), daemon=True).start()
    threading.Thread(target=divert, args=(FILTER_I, lambda: R_I, packet_freeze, lambda: freeze_mode), daemon=True).start()
    
    # Запускаем HTTP сервер
    server = http.server.HTTPServer(('127.0.0.1', 7777), RequestHandler)
    server.serve_forever()

if __name__ == "__main__":
    start_server()