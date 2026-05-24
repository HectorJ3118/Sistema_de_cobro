import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import serial
import serial.tools.list_ports
import threading
import time

class BilleteroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Control de Billetero CXB2 - Energizer")
        self.root.geometry("500x600")
        self.root.configure(padx=10, pady=10)
        self.procesando_billete = False

        self.ser = None
        self.is_connected = False
        self.thread_running = False

        # Mapeo MDB Escrow -> Valor en Pesos
        self.MDB_BILLS = {
            0x80: 20,
            0x81: 50,
            0x82: 100,
            0x83: 200,
            0x84: 500
        }

        # Variables de los Checkboxes (1 = Aceptar, 0 = Rechazar)
        self.acepta_billetes = {
            20: tk.BooleanVar(value=True),
            50: tk.BooleanVar(value=True),
            100: tk.BooleanVar(value=True),
            200: tk.BooleanVar(value=True),
            500: tk.BooleanVar(value=True)
        }

        self.setup_ui()
        self.refresh_ports()

    def setup_ui(self):
        # --- FRAME DE CONEXIÓN ---
        frame_conn = ttk.LabelFrame(self.root, text=" 🔌 Conexión Serial (Windows) ")
        frame_conn.pack(fill="x", pady=5)

        self.cb_ports = ttk.Combobox(frame_conn, state="readonly", width=12)
        self.cb_ports.grid(row=0, column=0, padx=10, pady=10)

        self.btn_refresh = ttk.Button(frame_conn, text="🔄", command=self.refresh_ports, width=3)
        self.btn_refresh.grid(row=0, column=1, padx=5)

        self.btn_connect = ttk.Button(frame_conn, text="Conectar", command=self.toggle_connection)
        self.btn_connect.grid(row=0, column=2, padx=10)

        self.lbl_status = ttk.Label(frame_conn, text="Desconectado", foreground="red", font=("Arial", 10, "bold"))
        self.lbl_status.grid(row=0, column=3, padx=10)

        # --- FRAME DE CONFIGURACIÓN DE BILLETES ---
        frame_config = ttk.LabelFrame(self.root, text=" 💵 Billetes Permitidos ")
        frame_config.pack(fill="x", pady=10)

        ttk.Label(frame_config, text="Selecciona qué billetes aceptará la máquina:", font=("Arial", 9)).grid(row=0, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        row_idx = 1
        for valor, var in self.acepta_billetes.items():
            chk = ttk.Checkbutton(frame_config, text=f"Aceptar ${valor}.00", variable=var)
            chk.grid(row=row_idx, column=0, sticky="w", padx=20, pady=2)
            row_idx += 1

        # --- FRAME DE LOGS ---
        frame_log = ttk.LabelFrame(self.root, text=" 📝 Consola de Eventos ")
        frame_log.pack(fill="both", expand=True, pady=5)

        self.log_box = scrolledtext.ScrolledText(frame_log, width=50, height=15, state="disabled", bg="#000000", fg="#00FF00", font=("Consolas", 10))
        self.log_box.pack(padx=5, pady=5, fill="both", expand=True)

    def log(self, mensaje):
        self.log_box.config(state="normal")
        hora = time.strftime("%H:%M:%S")
        self.log_box.insert(tk.END, f"[{hora}] {mensaje}\n")
        self.log_box.see(tk.END)
        self.log_box.config(state="disabled")

    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        self.cb_ports['values'] = [port.device for port in ports]
        if self.cb_ports['values']:
            self.cb_ports.current(0)

    def calcular_crc(self, payload):
        return sum(payload) & 0xFF

    def enviar_trama(self, payload):
        if self.ser and self.ser.is_open:
            crc = self.calcular_crc(payload)
            trama = [0xF1] + payload + [crc]
            self.ser.write(bytearray(trama))
            self.log(f"TX: {' '.join([format(b, '02X') for b in trama])}")

    def toggle_connection(self):
        if not self.is_connected:
            puerto = self.cb_ports.get()
            if not puerto:
                messagebox.showerror("Error", "Selecciona un puerto COM.")
                return
            try:
                self.ser = serial.Serial(puerto, 115200, timeout=0.1)
                self.is_connected = True
                self.btn_connect.config(text="Desconectar")
                self.cb_ports.config(state="disabled")
                self.btn_refresh.config(state="disabled")
                self.lbl_status.config(text="Conectado", foreground="green")
                self.log(f"Conectado a {puerto}.")
                
                # Iniciar el hilo de escucha MDB
                self.thread_running = True
                self.rx_thread = threading.Thread(target=self.serial_listener, daemon=True)
                self.rx_thread.start()

                # Despertar y habilitar el Billetero (0xC0)
                self.root.after(1500, self.habilitar_billetero)

            except Exception as e:
                messagebox.showerror("Error", f"No se pudo abrir el puerto: {e}")
        else:
            self.is_connected = False
            self.thread_running = False
            if self.ser:
                self.ser.close()
            self.btn_connect.config(text="Conectar")
            self.cb_ports.config(state="readonly")
            self.btn_refresh.config(state="normal")
            self.lbl_status.config(text="Desconectado", foreground="red")
            self.log("Desconectado.")

    def habilitar_billetero(self):
        self.log("Enviando comando de encendido al CXB2...")
        # Comando 0xC0: Habilitar billetero general
        payload = [0xC0, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF2]
        self.enviar_trama(payload)

    def decidir_billete(self, mdb_code):
        valor_billete = self.MDB_BILLS.get(mdb_code)
        
        if valor_billete is None:
            self.log(f"⚠️ Billete desconocido en Escrow (Código: {hex(mdb_code)}). Rechazando por seguridad.")
            self.responder_escrow(aceptar=False)
            return

        self.log(f"Billete de ${valor_billete} detectado en Escrow.")
        
        # Revisar si el checkbox de ese valor está marcado
        if self.acepta_billetes[valor_billete].get():
            self.log(f"✅ Software permite billete de ${valor_billete}. ACEPTANDO.")
            self.responder_escrow(aceptar=True)
        else:
            self.log(f"❌ Software bloquea billete de ${valor_billete}. RECHAZANDO.")
            self.responder_escrow(aceptar=False)

    def responder_escrow(self, aceptar):
        # Comando 0xC4: Control de Escrow. DAT1=0x01 (Aceptar), DAT1=0x00 (Rechazar)
        accion = 0x01 if aceptar else 0x00
        payload = [0xC4, accion, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF2]
        self.enviar_trama(payload)

    def serial_listener(self):
        buffer = b''
        while self.thread_running:
            try:
                if self.ser and self.ser.in_waiting > 0:
                    buffer += self.ser.read(self.ser.in_waiting)
                    
                    # Buscar tramas de 14 bytes
                    while b'\x02' in buffer:
                        inicio = buffer.find(b'\x02')
                        if len(buffer) >= inicio + 14:
                            trama = buffer[inicio:inicio+14]
                            buffer = buffer[inicio+14:] 
                            self.root.after(0, self.analizar_trama, trama)
                        else:
                            break
                time.sleep(0.05)
            except Exception as e:
                self.thread_running = False
                self.root.after(0, self.log, f"Error serial: {e}")

    def analizar_trama(self, trama):
        comando = trama[1]

        if comando == 0xB0: # Billete en Escrow
            # Solo procesamos si NO estamos ocupados tragando un billete
            if not self.procesando_billete:
                self.procesando_billete = True
                mdb_code = trama[2]
                self.decidir_billete(mdb_code)
            
        elif comando == 0xD4: # Respuesta a la instrucción Escrow (Apilado o Rechazado)
            if trama[2] == 0x01: # Asumiendo que DAT1=0x01 es éxito (ingresado)
                self.log("✅ Billete guardado exitosamente en la caja de seguridad.")
            else:
                self.log("↩️ Billete devuelto al usuario.")
            
            # Liberamos el candado para que pueda aceptar el siguiente billete
            self.procesando_billete = False
            
        elif comando == 0xD1: # Respuesta de inicialización 0xC0
            self.log("Billetero habilitado y en línea.")
            
        elif trama[1] == 0xD1: # Respuesta de inicialización 0xC0
            self.log("Billetero habilitado y en línea.")

if __name__ == "__main__":
    root = tk.Tk()
    app = BilleteroApp(root)
    
    def on_closing():
        app.thread_running = False
        if app.ser:
            app.ser.close()
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()