import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import serial
import serial.tools.list_ports
import threading
import time

class BoardDroidApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Panel de Control BoardDroid ")
        self.root.geometry("600x650")
        self.root.configure(padx=10, pady=10)
        self.procesando_billete = False

        # Variables de estado
        self.ser = None
        self.is_connected = False
        self.thread_running = False
        self.inventario = {10.0: 0, 5.0: 0, 2.0: 0, 1.0: 0}

        self.setup_ui()
        self.refresh_ports()

    def setup_ui(self):
        # --- FRAME DE CONEXIÓN ---
        frame_conn = ttk.LabelFrame(self.root, text=" 🔌 Conexión Serial (Windows) ")
        frame_conn.pack(fill="x", pady=5)

        ttk.Label(frame_conn, text="Puerto COM:").grid(row=0, column=0, padx=5, pady=10)
        self.cb_ports = ttk.Combobox(frame_conn, state="readonly", width=15)
        self.cb_ports.grid(row=0, column=1, padx=5)

        self.btn_refresh = ttk.Button(frame_conn, text="🔄 Refrescar", command=self.refresh_ports)
        self.btn_refresh.grid(row=0, column=2, padx=5)

        self.btn_connect = ttk.Button(frame_conn, text="Conectar", command=self.toggle_connection)
        self.btn_connect.grid(row=0, column=3, padx=10)

        self.lbl_status = ttk.Label(frame_conn, text="Desconectado", foreground="red")
        self.lbl_status.grid(row=0, column=4, padx=5)

        # --- FRAME DE INVENTARIO ---
        frame_inv = ttk.LabelFrame(self.root, text=" 🪙 Inventario de Monedero Gryphon ")
        frame_inv.pack(fill="x", pady=10)

        self.lbl_monedas = {}
        row_idx = 0
        for den in [10.0, 5.0, 2.0, 1.0]:
            ttk.Label(frame_inv, text=f"Monedas de ${den:.2f}:", font=("Arial", 10, "bold")).grid(row=row_idx, column=0, sticky="e", padx=10, pady=5)
            self.lbl_monedas[den] = ttk.Label(frame_inv, text="0", font=("Arial", 10))
            self.lbl_monedas[den].grid(row=row_idx, column=1, sticky="w", padx=10)
            row_idx += 1

        ttk.Separator(frame_inv, orient='horizontal').grid(row=row_idx, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Label(frame_inv, text="TOTAL:", font=("Arial", 12, "bold"), foreground="blue").grid(row=row_idx+1, column=0, sticky="e", padx=10, pady=5)
        self.lbl_total = ttk.Label(frame_inv, text="$0.00", font=("Arial", 12, "bold"), foreground="blue")
        self.lbl_total.grid(row=row_idx+1, column=1, sticky="w", padx=10)

        self.btn_read_inv = ttk.Button(frame_inv, text="Actualizar Inventario Manual", command=self.solicitar_inventario, state="disabled")
        self.btn_read_inv.grid(row=row_idx+2, column=0, columnspan=2, pady=10)

        # --- FRAME DE DISPENSADO ---
        frame_disp = ttk.LabelFrame(self.root, text=" 💸 Dispensar Cambio ")
        frame_disp.pack(fill="x", pady=5)

        ttk.Label(frame_disp, text="Monto a regresar: $").grid(row=0, column=0, padx=5, pady=10)
        self.entry_monto = ttk.Entry(frame_disp, width=15)
        self.entry_monto.grid(row=0, column=1, padx=5)

        self.btn_dispense = ttk.Button(frame_disp, text="Dar Cambio", command=self.procesar_cambio, state="disabled")
        self.btn_dispense.grid(row=0, column=2, padx=10)

        # --- FRAME DE LOGS (Registro de eventos) ---
        frame_log = ttk.LabelFrame(self.root, text=" 📝 Registro de Eventos (Consola) ")
        frame_log.pack(fill="both", expand=True, pady=5)

        self.log_box = scrolledtext.ScrolledText(frame_log, width=60, height=10, state="disabled", bg="#1e1e1e", fg="#00ff00", font=("Consolas", 9))
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
                self.btn_read_inv.config(state="normal")
                self.btn_dispense.config(state="normal")
                self.log(f"Conectado a {puerto} exitosamente.")
                
                # Iniciar el hilo de escucha
                self.thread_running = True
                self.rx_thread = threading.Thread(target=self.serial_listener, daemon=True)
                self.rx_thread.start()

                # Solicitar inventario inicial tras conexión
                self.root.after(1500, self.solicitar_inventario)

            except Exception as e:
                messagebox.showerror("Error de Conexión", f"No se pudo abrir el puerto: {e}")
        else:
            self.is_connected = False
            self.thread_running = False
            if self.ser:
                self.ser.close()
            self.btn_connect.config(text="Conectar")
            self.cb_ports.config(state="readonly")
            self.btn_refresh.config(state="normal")
            self.lbl_status.config(text="Desconectado", foreground="red")
            self.btn_read_inv.config(state="disabled")
            self.btn_dispense.config(state="disabled")
            self.log("Desconectado del puerto.")

    def calcular_crc(self, payload):
        return sum(payload) & 0xFF

    def enviar_trama(self, payload):
        if self.ser and self.ser.is_open:
            crc = self.calcular_crc(payload)
            trama = [0xF1] + payload + [crc]
            self.ser.write(bytearray(trama))
            self.log(f"TX: {' '.join([format(b, '02X') for b in trama])}")

    def solicitar_inventario(self):
        self.log("Solicitando inventario de tubos...")
        payload = [0xC2, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF2]
        self.enviar_trama(payload)

    def actualizar_ui_inventario(self, dat3, dat4, dat5, dat6):
        # Mapeo según la placa: DAT3=$1, DAT4=$2, DAT5=$5, DAT6=$10
        self.inventario[1.0] = dat3
        self.inventario[2.0] = dat4
        self.inventario[5.0] = dat5
        self.inventario[10.0] = dat6

        total = 0.0
        for den in self.inventario:
            cant = self.inventario[den]
            self.lbl_monedas[den].config(text=str(cant))
            total += (cant * den)

        self.lbl_total.config(text=f"${total:.2f}")

    def procesar_cambio(self):
        monto_str = self.entry_monto.get()
        try:
            cambio_solicitado = float(monto_str)
        except ValueError:
            messagebox.showwarning("Atención", "Ingresa una cantidad numérica válida.")
            return

        resto = cambio_solicitado
        entrega = {10.0: 0, 5.0: 0, 2.0: 0, 1.0: 0}
        inv_temp = self.inventario.copy()
        
        # Algoritmo voraz verificando stock
        for den in [10.0, 5.0, 2.0, 1.0]:
            while resto >= den and inv_temp[den] > 0:
                entrega[den] += 1
                inv_temp[den] -= 1
                resto = round(resto - den, 2)

        if resto > 0:
            messagebox.showerror("Error de Stock", f"Monedas insuficientes en los tubos.\nFaltarían ${resto:.2f} por entregar.")
            return

        # Proceder a construir la trama
        self.log(f"Dispensando: $10({entrega[10.0]}), $5({entrega[5.0]}), $2({entrega[2.0]}), $1({entrega[1.0]})")
        
        # Trama: CMD(C6), DAT1($0.5), DAT2($1), DAT3($2), DAT4($5), DAT5($10)
        # Nota: Ajustamos el índice en el payload para el comando 0xC6 de escritura
        payload = [0xC6, 0x00, entrega[1.0], entrega[2.0], entrega[5.0], entrega[10.0], 0x00, 0x00, 0x00, 0xF2]
        self.enviar_trama(payload)
        self.entry_monto.delete(0, tk.END)

        # Solicitar actualización de inventario unos segundos después de pagar
        self.root.after(3000, self.solicitar_inventario)

    def serial_listener(self):
        """ Hilo en segundo plano que escucha constantemente el puerto """
        buffer = b''
        while self.thread_running:
            try:
                if self.ser and self.ser.in_waiting > 0:
                    buffer += self.ser.read(self.ser.in_waiting)
                    
                    # Buscar tramas completas de 14 bytes (inician con 0x02)
                    while b'\x02' in buffer:
                        inicio = buffer.find(b'\x02')
                        if len(buffer) >= inicio + 14:
                            trama = buffer[inicio:inicio+14]
                            buffer = buffer[inicio+14:] # Limpiar buffer
                            
                            # Procesar la trama en el hilo principal de Tkinter
                            self.root.after(0, self.analizar_trama, trama)
                        else:
                            # Aún no llegan los 14 bytes completos
                            break
                time.sleep(0.05) # Pequeña pausa para no saturar el procesador
            except Exception as e:
                self.thread_running = False
                self.root.after(0, self.log, f"Error en lectura serial: {e}")

    def analizar_trama(self, trama):
        self.log(f"RX: {' '.join([format(b, '02X') for b in trama])}")
        
        if trama[1] == 0xD2: # Respuesta de Inventario
            self.actualizar_ui_inventario(dat3=trama[4], dat4=trama[5], dat5=trama[6], dat6=trama[7])
            self.log("Inventario actualizado.")
            
        elif trama[1] == 0xA0: # Moneda Insertada
            valor_ascii = int((trama[2] - 0x30)*1000 + (trama[3] - 0x30)*100 + (trama[4] - 0x30)*10 + (trama[5] - 0x30)) / 10
            self.log(f"*** EVENTO: Moneda de ${valor_ascii:.2f} insertada ***")
            self.root.after(1000, self.solicitar_inventario) # Refrescar tubos

        elif trama[1] == 0xB0: # Billete Insertado (Escrow)
            self.log("*** EVENTO: Billete en Escrow (Validando) ***")
            # Podrías agregar aquí el comando para Aceptar Automáticamente (0xC4)

if __name__ == "__main__":
    root = tk.Tk()
    app = BoardDroidApp(root)
    
    # Manejar cierre seguro de la ventana
    def on_closing():
        app.thread_running = False
        if app.ser:
            app.ser.close()
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()