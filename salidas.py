import serial
import time

print("🔌 --- TESTER HEXADECIMAL BOARDDROID (MOTORES/AX) --- 🔌")
puerto = input("Ingresa el puerto de tu placa (ej. COM3): ").strip()

try:
    ser = serial.Serial(puerto, 9600, timeout=1)
    print(f"\n✅ Conectado a {puerto}")
    print("💡 Escribe los bytes en Hexadecimal separados por espacio.")
    print("Ejemplo sugerido: C7 01 (Comando Motor + Motor 1/AX1)")
    print("Escribe 'salir' para terminar.\n")

    while True:
        comando_texto = input("Hex > ").strip()
        
        if comando_texto.lower() == 'salir':
            break
        if not comando_texto:
            continue

        try:
            # Convertimos el texto (ej. "C7 01") a bytes reales de hardware
            comando_bytes = bytes.fromhex(comando_texto)
            ser.write(comando_bytes)
            print(f"  ➡️ Enviado (Bytes): {comando_bytes.hex().upper()}")
            
            time.sleep(0.5)
            
            # Leemos la respuesta de la placa en Hexadecimal
            if ser.in_waiting > 0:
                respuesta = ser.read(ser.in_waiting)
                print(f"  ⬅️ Respuesta de placa: {respuesta.hex().upper()}")
            else:
                print("  ⬅️ (Sin respuesta)")
                
        except ValueError:
            print("  ❌ Error: Formato inválido. Escribe solo números y letras Hex (ej. C7 01)")

except Exception as e:
    print(f"\n❌ Error de puerto: {e}")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()
        print("✅ Puerto cerrado.")