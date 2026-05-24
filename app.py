from flask import Flask, render_template, request
from flask_socketio import SocketIO
import serial
import serial.tools.list_ports
import threading
import time
import mariadb
from datetime import datetime
import os
from fpdf import FPDF
from flask import Flask, render_template, request, session, redirect, url_for


app = Flask(__name__)
# async_mode='threading' permite que el bucle de la placa no choque con el servidor web
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")
app.secret_key = '6867'
# Variables de estado global
estado_hardware = {
    'ser': None,
    'conectado': False,
    'hilo_activo': False,
    'venta_activa': False, # NUEVO: Control estricto de seguridad para el billetero
    'inventario': {10.0: 0, 5.0: 0, 2.0: 0, 1.0: 0}
}

# Mapeos de denominaciones
MAPEO_ESCROW = {0x90: 20, 0x91: 50, 0x92: 100, 0x93: 200, 0x95: 500}
MAPEO_STACKED = {0x80: 20, 0x81: 50, 0x82: 100, 0x83: 200, 0x85: 500}

def get_db_connection():
    try:
        conn = mariadb.connect(
            host="localhost",
            user="root",        # Tu usuario de MariaDB
            password="",        # Tu contraseña de MariaDB
            database="boarddroid_pos"
        )
        return conn
    except mariadb.Error as e:
        print(f"Error conectando a MariaDB: {e}")
        return None
    
def es_consulta_segura(sql_comando):
    """
    Verifica si una sentencia UPDATE o DELETE contiene la cláusula WHERE.
    Retorna True si es segura o no es de modificación, False si es peligrosa.
    """
    sql_limpio = sql_comando.strip().lower()
    
    # Si la consulta intenta actualizar o borrar
    if sql_limpio.startswith("update") or sql_limpio.startswith("delete"):
        if "where" not in sql_limpio:
            print("⚠️ ¡BLOQUEO DE SEGURIDAD! Intento de ejecución de UPDATE/DELETE sin WHERE.")
            return False
            
    return True    

def calcular_crc(payload):
    return sum(payload) & 0xFF

def enviar_trama(payload):
    if estado_hardware['ser'] and estado_hardware['ser'].is_open:
        crc = calcular_crc(payload)
        trama = [0xF1] + payload + [crc]
        estado_hardware['ser'].write(bytearray(trama))
        # print(f"TX: {' '.join([format(b, '02X') for b in trama])}")

def serial_listener():
    buffer = b''
    while estado_hardware['hilo_activo']:
        try:
            if estado_hardware['ser'] and estado_hardware['ser'].in_waiting > 0:
                buffer += estado_hardware['ser'].read(estado_hardware['ser'].in_waiting)
                while b'\x02' in buffer:
                    inicio = buffer.find(b'\x02')
                    if len(buffer) >= inicio + 14:
                        trama = buffer[inicio:inicio+14]
                        buffer = buffer[inicio+14:]
                        analizar_trama(trama)
                    else:
                        break
            time.sleep(0.05)
        except Exception as e:
            print(f"Error serial: {e}")
            estado_hardware['hilo_activo'] = False

def analizar_trama(trama):
    cmd = trama[1]
    
    if cmd == 0xD2: # INVENTARIO
        estado_hardware['inventario'][1.0] = trama[4]
        estado_hardware['inventario'][2.0] = trama[5]
        estado_hardware['inventario'][5.0] = trama[6]
        estado_hardware['inventario'][10.0] = trama[7]
        socketio.emit('inventario_actualizado', estado_hardware['inventario'])
        
    elif cmd == 0xA0: # MONEDA INSERTADA
        byte_moneda = trama[2]
        tipo = byte_moneda & 0x0F
        mapeo = {0x02: 1.0, 0x03: 2.0, 0x04: 5.0, 0x05: 10.0}
        
        if tipo in mapeo:
            valor = mapeo[tipo]
            print(f"Moneda ingresada: ${valor}")
            socketio.emit('dinero_ingresado', {'valor': valor, 'tipo': 'moneda'})
            time.sleep(1)
            enviar_trama([0xC2, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF2])

    elif cmd == 0xB0: # BILLETE INSERTADO
        byte_billete = trama[2]
        
        # CASO A: Billete retenido (Escrow)
        if byte_billete in MAPEO_ESCROW:
            if estado_hardware['venta_activa']:
                print("Billete en validación. Ordenando ACEPTAR...")
                enviar_trama([0xC4, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF2])
            else:
                print("⚠️ Billete detectado sin cobro iniciado. RECHAZANDO...")
                enviar_trama([0xC4, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF2])
                
        # CASO B: Billete asegurado (Stacked)
        elif byte_billete in MAPEO_STACKED:
            valor = MAPEO_STACKED[byte_billete]
            print(f"Billete guardado: ${valor}")
            socketio.emit('dinero_ingresado', {'valor': valor, 'tipo': 'billete'})

# ================= RUTAS WEB =================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/puertos')
def get_puertos():
    puertos = [port.device for port in serial.tools.list_ports.comports()]
    return {'puertos': puertos}

@app.route('/api/estado_venta', methods=['POST'])
def cambiar_estado_venta():
    """ El Frontend avisa aquí si hay un cobro en curso para habilitar el billetero """
    datos = request.json
    estado_hardware['venta_activa'] = datos.get('activa', False)
    return {'status': 'ok'}

@app.route('/api/conectar', methods=['POST'])
def conectar():
    datos = request.json
    puerto = datos.get('puerto')
    if not estado_hardware['conectado']:
        try:
            estado_hardware['ser'] = serial.Serial(puerto, 115200, timeout=0.1)
            estado_hardware['conectado'] = True
            estado_hardware['hilo_activo'] = True
            threading.Thread(target=serial_listener, daemon=True).start()
            
            # Habilitar monedero y billetero
            time.sleep(1.0)
            enviar_trama([0xC0, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF2])
            time.sleep(0.5)
            enviar_trama([0xC1, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF2])
            time.sleep(0.5)
            enviar_trama([0xC2, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF2])
            return {'status': 'ok', 'msg': f'Conectado a {puerto}'}
        except Exception as e:
            return {'status': 'error', 'msg': str(e)}, 500
    return {'status': 'ok', 'msg': 'Ya estaba conectado'}

@app.route('/api/inventario', methods=['POST'])
def actualizar_inventario_manual():
    if estado_hardware['conectado']:
        enviar_trama([0xC2, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF2])
        return {'status': 'ok'}
    return {'status': 'error'}, 400

@app.route('/api/dispensar', methods=['POST'])
def dispensar():
    datos = request.json
    cambio_monedas = datos.get('monto')
    
    resto = float(cambio_monedas)
    entrega = {10.0: 0, 5.0: 0, 2.0: 0, 1.0: 0}
    inv_temp = estado_hardware['inventario'].copy()
    
    for den in [10.0, 5.0, 2.0, 1.0]:
        while resto >= den and inv_temp[den] > 0:
            entrega[den] += 1
            inv_temp[den] -= 1
            resto = round(resto - den, 2)

    if resto > 0:
        return {'status': 'error', 'msg': f'Faltan ${resto:.2f} en tubos.'}, 400

    payload = [0xC6, 0x00, entrega[1.0], entrega[2.0], entrega[5.0], entrega[10.0], 0x00, 0x00, 0x00, 0xF2]
    enviar_trama(payload)
    return {'status': 'ok'}

@app.route('/api/vendedores', methods=['GET'])
def obtener_vendedores():
    conn = get_db_connection()
    if not conn: return {'vendedores': []}
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nombre FROM vendedores WHERE activo = TRUE")
    vendedores = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return {'vendedores': vendedores}

@app.route('/api/guardar_venta', methods=['POST'])
def guardar_venta():
    datos = request.json
    monto_vendido = datos.get('monto_vendido')
    monto_pagado = datos.get('monto_pagado')
    vendedor_id = datos.get('vendedor_id')
    metodo_pago = datos.get('metodo_pago', 'efectivo') # NUEVO: Recibimos el método

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO ventas (monto_vendido, monto_pagado, vendedor_id, metodo_pago) VALUES (?, ?, ?, ?)"
        cursor.execute(sql, (monto_vendido, monto_pagado, vendedor_id, metodo_pago))
        conn.commit()
        
        cursor.close()
        conn.close()

        socketio.emit('notificar_nueva_venta', {'monto': monto_vendido})
        return {'status': 'ok', 'msg': 'Venta registrada exitosamente'}
    except Exception as e:
        print(f"Error guardando venta: {e}")
        return {'status': 'error', 'msg': str(e)}, 500
    
if not os.path.exists('static/cortes'):
    os.makedirs('static/cortes')

@app.route('/api/metricas', methods=['GET'])
def obtener_metricas():
    conn = get_db_connection()
    if not conn:
        return {'hoy': 0, 'transacciones': 0, 'por_vendedor': [], 'ventas_tiempo': [], 'por_metodo': []}
        
    cursor = conn.cursor(dictionary=True)
    
    # 1. Métricas de hoy (AHORA SOLO CUENTA LAS VENTAS SIN CORTE)
    cursor.execute("SELECT SUM(monto_vendido) as total_hoy, COUNT(id) as transacciones FROM ventas WHERE corte_id IS NULL")
    hoy = cursor.fetchone()
    total_hoy = float(hoy['total_hoy']) if hoy and hoy['total_hoy'] is not None else 0.0
    transacciones = hoy['transacciones'] if hoy and hoy['transacciones'] is not None else 0

    # 2. Rendimiento por vendedor (del turno actual)
    cursor.execute("SELECT v.nombre, SUM(ve.monto_vendido) as total_vendido FROM ventas ve JOIN vendedores v ON ve.vendedor_id = v.id WHERE ve.corte_id IS NULL GROUP BY v.id")
    por_vendedor = [{'nombre': r['nombre'], 'total_vendido': float(r['total_vendido']) if r['total_vendido'] else 0.0} for r in cursor.fetchall()]

    # 3. Ingresos por Método (del turno actual)
    cursor.execute("SELECT metodo_pago, SUM(monto_vendido) as total FROM ventas WHERE corte_id IS NULL GROUP BY metodo_pago")
    por_metodo = [{'metodo': r['metodo_pago'], 'total': float(r['total']) if r['total'] else 0.0} for r in cursor.fetchall()]

    # 4. Ventas Históricas en el tiempo (ESTA NO SE REINICIA, LEE TODO EL HISTORIAL)
    cursor.execute("SELECT DATE_FORMAT(fecha_hora, '%d/%m/%Y') as fecha, SUM(monto_vendido) as total FROM ventas GROUP BY DATE(fecha_hora) ORDER BY DATE(fecha_hora) DESC LIMIT 7")
    ventas_tiempo = [{'fecha': r['fecha'], 'total': float(r['total']) if r['total'] else 0.0} for r in cursor.fetchall()]
    ventas_tiempo.reverse()

    cursor.close()
    conn.close()
    
    return {
        'hoy': total_hoy,
        'transacciones': transacciones,
        'por_vendedor': por_vendedor,
        'ventas_tiempo': ventas_tiempo,
        'por_metodo': por_metodo
    }

@app.route('/api/corte_caja', methods=['POST'])
def hacer_corte():
    datos = request.json
    pin = datos.get('pin')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Validar que sea Administrador
    cursor.execute("SELECT id FROM vendedores WHERE rol = 'admin' AND pin = ?", (pin,))
    if not cursor.fetchone():
        return {'status': 'error', 'msg': 'PIN de administrador incorrecto'}, 401
    
    # 2. Obtener todas las ventas que no tienen corte
    cursor.execute("""
        SELECT v.id, v.monto_vendido, v.metodo_pago, v.fecha_hora, vend.nombre 
        FROM ventas v JOIN vendedores vend ON v.vendedor_id = vend.id 
        WHERE v.corte_id IS NULL
    """)
    ventas = cursor.fetchall()
    
    if not ventas:
        return {'status': 'error', 'msg': 'No hay ventas registradas en este turno para hacer corte.'}, 400
        
    # 3. Calcular totales
    total_ef = sum(float(v['monto_vendido']) for v in ventas if v['metodo_pago'] == 'efectivo')
    total_ta = sum(float(v['monto_vendido']) for v in ventas if v['metodo_pago'] == 'tarjeta')
    total_tr = sum(float(v['monto_vendido']) for v in ventas if v['metodo_pago'] == 'transferencia')
    total_general = total_ef + total_ta + total_tr

    # 4. Generar el documento PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, txt="Corte de Caja - BoardDroid POS", ln=True, align='C')
    pdf.set_font("Arial", size=12)
    fecha_corte = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    pdf.cell(190, 10, txt=f"Fecha y Hora de Cierre: {fecha_corte}", ln=True, align='C')
    pdf.ln(5)
    
    # Resumen Financiero
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(190, 10, txt=f"INGRESOS TOTALES: ${total_general:.2f}", ln=True, align='L')
    pdf.set_font("Arial", size=11)
    pdf.cell(190, 8, txt=f"Efectivo en Caja: ${total_ef:.2f}", ln=True, align='L')
    pdf.cell(190, 8, txt=f"Pagos con Tarjeta: ${total_ta:.2f}", ln=True, align='L')
    pdf.cell(190, 8, txt=f"Transferencias: ${total_tr:.2f}", ln=True, align='L')
    pdf.ln(10)
    
    # Tabla de Ventas Individuales
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(20, 10, 'ID', 1)
    pdf.cell(50, 10, 'Cajero', 1)
    pdf.cell(40, 10, 'Metodo', 1)
    pdf.cell(30, 10, 'Hora', 1)
    pdf.cell(30, 10, 'Monto', 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=10)
    for v in ventas:
        pdf.cell(20, 10, str(v['id']), 1)
        pdf.cell(50, 10, v['nombre'], 1)
        pdf.cell(40, 10, v['metodo_pago'].upper(), 1)
        pdf.cell(30, 10, v['fecha_hora'].strftime("%H:%M"), 1)
        pdf.cell(30, 10, f"${float(v['monto_vendido']):.2f}", 1)
        pdf.ln()
        
    nombre_archivo = f"corte_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    ruta_pdf = f"static/cortes/{nombre_archivo}"
    pdf.output(ruta_pdf)
    
    # 5. Guardar el registro del corte y actualizar las ventas
    cursor.execute("INSERT INTO cortes_caja (total_vendido, ruta_pdf) VALUES (?, ?)", (total_general, f"/{ruta_pdf}"))
    corte_id = cursor.lastrowid
    cursor.execute("UPDATE ventas SET corte_id = ? WHERE corte_id IS NULL", (corte_id,))
    conn.commit()
    
    cursor.close()
    conn.close()
    
    # Avisamos al Dashboard para que ponga los números en $0.00
    socketio.emit('notificar_nueva_venta', {'monto': 0})
    
    return {'status': 'ok', 'pdf_url': f"/{ruta_pdf}"}

@app.route('/dashboard')
def dashboard():
    # Si la sesión no existe, manda a la vista bonita de Tailwind de bloqueo
    if not session.get('es_admin'):
        return render_template('bloqueo.html', destino="el Dashboard")
    return render_template('dashboard.html')

@app.route('/logout_admin')
def logout_admin():
    session.pop('es_admin', None) # CERRAR SESIÓN
    return redirect('/')
@app.route('/api/login', methods=['POST'])
def login():
    datos = request.json
    vendedor_id = datos.get('vendedor_id')
    pin = datos.get('pin')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # Verificamos si el ID y el PIN coinciden
    cursor.execute("SELECT id, nombre, rol FROM vendedores WHERE id = ? AND pin = ?", (vendedor_id, pin))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if user:
        return {'status': 'ok', 'user': user}
    return {'status': 'error', 'msg': 'PIN incorrecto'}, 401

@app.route('/api/auth_admin', methods=['POST'])
def auth_admin():
    datos = request.json
    pin = datos.get('pin')
    
    conn = get_db_connection()
    if not conn: return {'status': 'error', 'msg': 'Error de base de datos'}, 500
    cursor = conn.cursor(dictionary=True)
    
    # Búsqueda Global: ¿Existe ALGÚN administrador con este PIN? (Llave Maestra)
    cursor.execute("SELECT id FROM vendedores WHERE rol = 'admin' AND pin = ?", (pin,))
    admin = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if admin:
        session['es_admin'] = True  # Activación del token de sesión seguro
        return {'status': 'ok'}
    return {'status': 'error', 'msg': 'PIN de Administrador inválido'}, 401

@app.route('/empleados')
def gestion_empleados():
    # Lo mismo para la vista de empleados
    if not session.get('es_admin'):
        return render_template('bloqueo.html', destino="la Gestión de Personal")
    return render_template('empleados.html')

@app.route('/api/todos_los_empleados', methods=['GET'])
def obtener_todos_empleados():
    conn = get_db_connection()
    if not conn: return {'empleados': []}
    cursor = conn.cursor(dictionary=True)
    # Traemos todos, incluso los inactivos, para que el admin vea todo el historial
    cursor.execute("SELECT id, nombre, rol, activo, pin FROM vendedores")
    empleados = cursor.fetchall()
    cursor.close()
    conn.close()
    return {'empleados': empleados}

@app.route('/api/agregar_empleado', methods=['POST'])
def agregar_empleado():
    datos = request.json
    nombre = datos.get('nombre')
    pin = datos.get('pin')
    rol = datos.get('rol')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO vendedores (nombre, pin, rol, activo) VALUES (?, ?, ?, 1)"
        cursor.execute(sql, (nombre, pin, rol))
        conn.commit()
        cursor.close()
        conn.close()
        return {'status': 'ok', 'msg': 'Empleado agregado correctamente'}
    except Exception as e:
        return {'status': 'error', 'msg': str(e)}, 500

@app.route('/api/desactivar_empleado', methods=['POST'])
def desactivar_empleado():
    datos = request.json
    emp_id = datos.get('id')
    estado_nuevo = datos.get('activo') # 1 para activar, 0 para desactivar

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Borrado Lógico: Solo cambiamos el estado para no romper el historial de ventas
        cursor.execute("UPDATE vendedores SET activo = ? WHERE id = ?", (estado_nuevo, emp_id))
        conn.commit()
        cursor.close()
        conn.close()
        return {'status': 'ok'}
    except Exception as e:
        return {'status': 'error', 'msg': str(e)}, 500
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)