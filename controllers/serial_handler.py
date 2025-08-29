
# controllers/serial_handler.py
import json
import struct
import serial
from PySide6.QtCore import QObject, QTimer, Signal


class SerialHandler(QObject):
    """
    Gestion série monothread via QTimer.
    Lit en polling et émet des signaux pour JSON et données binaires.
    """
    json_received    = Signal(dict)
    data_received    = Signal(float, float, float)
    error            = Signal(str)
    line_received    = Signal(str)      # toute ligne brute reçue
    command_sent     = Signal(object)   # dict JSON envoyé
    event_received   = Signal(str)      # champ "event" d’un JSON reçu

    def __init__(self, parent=None, poll_interval_ms=50):
        super().__init__(parent)
        self.ser   = None
        self._buffer     = bytearray()  # un seul buffer mixte
        self._text_tail  = ""           # reste de la dernière ligne textuelle
        self.timer = QTimer(self)
        self.timer.setInterval(poll_interval_ms)
        self.timer.timeout.connect(self._read_serial)

  

    def open(self, port: str, baud: int = 115200):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = serial.Serial(port, baudrate=baud, timeout=0.1)
            self.timer.start()
        except Exception as e:
            self.ser = None  # Empêche toute lecture ensuite
            raise e
            
    def send_raw(self, data: bytes):
        """Envoie des octets bruts sur le port série."""
        if self.ser and self.ser.is_open:
            self.ser.write(data)
        else:
            self.error.emit("Port non ouvert : impossible d'envoyer de la donnée brute")

    def send(self, msg: dict):
        if not self.ser:
            return self.error.emit("Port non ouvert")
        try:
            payload = json.dumps(msg) + "\n"
            self.ser.write(payload.encode("utf-8"))
            self.ser.flush()           
            self.command_sent.emit(payload)
        except Exception as e:
            self.error.emit(f"Échec envoi : {e}")


  

    def _read_serial(self):
        START_BYTE = b'\xAA'
        PAYLOAD_LEN = 12
        FRAME_LEN   = PAYLOAD_LEN + 1  # checksum en plus
        # 1) lit tout ce qui est dispo
        try:
            if not self.ser or not hasattr(self.ser, 'is_open') or not self.ser.is_open:
                return  # Empêche toute lecture si le port est invalide
            avail = self.ser.in_waiting
        except (OSError, serial.SerialException, TypeError, AttributeError) as e:
            self.error.emit(f"Port invalide : {e}")
            self.ser = None  # Ajoute ça pour éviter que ça boucle ensuite
            return
        if avail == 0:
            return

        try:
            # 2) traite chaque frame texte OU binaire
            # tant que l'Arduino a envoyé au moins 1 octet
            while self.ser.in_waiting:
                head = self.ser.read(1)
                if head == START_BYTE:
                    # lecture stricte du payload + checksum
                    chunk = self.ser.read(PAYLOAD_LEN + 1)
                    if len(chunk) < PAYLOAD_LEN + 1:
                        # trame incomplète, on arrête et on remet head dans le buffer
                        #self.ser.unread(chunk)  # si supported, sinon stockez en buffer local
                        self.error.emit("Trame incomplète, ignorée.")
                        return

                    payload, recv_chk = chunk[:PAYLOAD_LEN], chunk[-1]
                    # vérification checksum
                    calc = START_BYTE[0]
                    for b in payload:
                        calc ^= b
                    if calc != recv_chk:
                        # trame corrompue : on l'ignore et on continue la boucle
                        continue

                    # unpack et émission
                    t, d, f = struct.unpack('<fff', payload)
                    if t == -1.0 and d == -1.0 and f == -1.0:
                        return
                    self.data_received.emit(t, d, f)
                else:
                    # on a lu un octet non binaire => texte
                    # on peut accumuler dans un buffer str si besoin
                    # ou
                    line = head + self.ser.readline()
                    self._handle_text_line(line)
        except Exception as e:
            self.error.emit(f"Erreur pendant la lecture série : {e}")
            return

    def _handle_text_line(self, raw: bytes):
        line = raw.decode('utf-8', errors='ignore').strip()
        self.line_received.emit(line)
        if line.startswith("{"):
            try:
                msg = json.loads(line)
                self.json_received.emit(msg)
                if evt := msg.get("event"):
                    self.event_received.emit(evt)
            except json.JSONDecodeError:
                pass
    def close(self):
        if self.timer.isActive(): self.timer.stop()
        if self.ser and self.ser.is_open: self.ser.close()    
    
    def stop(self):
        self._reading = False
        if self.ser and self.ser.is_open:
            self.ser.close()