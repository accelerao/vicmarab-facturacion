import streamlit as st
import pandas as pd
from datetime import date
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Sistema VICMARAB", layout="wide", page_icon="🛍️")
st.title("📊 VICMARAB - Sistema de Gestión")

MONEDA = "DOP"

# --- CONEXIÓN A GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNCIONES DE CARGA OPTIMIZADAS (CON CACHÉ) ---
# Esto evita el error "Quota Exceeded" (Error 429)

@st.cache_data(ttl=600) # Guarda en memoria 10 mins
def cargar_datos_sheets(hoja, columnas_esperadas):
    try:
        # Leemos sin ttl=0 para usar la caché
        df = conn.read(worksheet=hoja, usecols=columnas_esperadas)
        df = df.dropna(how="all")
        return df
    except Exception:
        return pd.DataFrame(columns=columnas_esperadas)

@st.cache_data(ttl=600)
def obtener_catalogo():
    try:
        df = conn.read(worksheet="Catalogo", usecols=[0, 1])
        df = df.dropna()
        if df.empty: return {}
        # Convertimos a diccionario: {"Producto": Precio}
        return dict(zip(df.iloc[:, 0], df.iloc[:, 1]))
    except Exception:
        return {}

# --- CARGA INICIAL ---
CATALOGO = obtener_catalogo()

# --- PESTAÑAS ---
tab1, tab2, tab3 = st.tabs(["🧾 Facturación", "💸 Registrar Gastos", "⚙️ Administración"])

# ==============================================================================
# PESTAÑA 1: FACTURACIÓN (CON MEMORIA DE CLIENTES + PRODUCTOS FLEXIBLES)
# ==============================================================================
with tab1:
    st.header("Nueva Factura")
    
    if 'factura_items' not in st.session_state:
        st.session_state.factura_items = pd.DataFrame(columns=["Descripción", "Cantidad", "Precio Unitario"])

    # --- 1. DATOS DEL CLIENTE (AUTORRELLENO) ---
    df_clientes_db = cargar_datos_sheets("Ventas", ["Cliente", "Telefono", "Direccion"])
    
    lista_clientes = []
    if not df_clientes_db.empty:
        df_unicos = df_clientes_db.drop_duplicates(subset=["Cliente"], keep="last")
        lista_clientes = sorted(df_unicos["Cliente"].dropna().astype(str).tolist())

    with st.expander("👤 Datos del Cliente", expanded=True):
        opcion_cliente = st.selectbox(
            "📂 Buscar Cliente Existente", 
            options=["-- Nuevo / Manual --"] + lista_clientes,
            index=0
        )

        val_nombre, val_tel, val_dir = "", "", ""

        if opcion_cliente != "-- Nuevo / Manual --":
            datos = df_clientes_db[df_clientes_db["Cliente"] == opcion_cliente].iloc[-1]
            val_nombre = str(datos["Cliente"])
            val_tel = str(datos.get("Telefono", "")).replace("nan", "")
            val_dir = str(datos.get("Direccion", "")).replace("nan", "")

        col1, col2 = st.columns(2)
        with col1:
            cliente_nombre = st.text_input("Nombre del Cliente", value=val_nombre, key="cli_nom")
            cliente_telefono = st.text_input("Número Telefónico", value=val_tel, key="cli_tel")
        with col2:
            fecha_factura = st.date_input("Fecha", date.today(), key="fecha_fac")
            cliente_direccion = st.text_input("Dirección de entrega", value=val_dir, key="cli_dir")

    st.divider()

    # --- 2. SELECCIÓN DE PRODUCTOS (HÍBRIDA) ---
    st.write("### Agregar Producto")
    lista_opciones = ["-- Selecciona un Producto --"] + list(CATALOGO.keys()) + ["-- Otro / Manual --"]

    def actualizar_precio_sesion():
        item = st.session_state.selector_producto_key
        if item in CATALOGO:
            st.session_state.input_precio_key = float(CATALOGO[item])
        elif item == "-- Selecciona un Producto --":
            st.session_state.input_precio_key = 0.0

    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
    with c1:
        prod_sel = st.selectbox("Producto", options=lista_opciones, key="selector_producto_key", on_change=actualizar_precio_sesion)
        
        nombre_final_producto = prod_sel
        if prod_sel == "-- Otro / Manual --":
            nombre_final_producto = st.text_input("Escribe el nombre:", placeholder="Ej. Servicio Especial")
        elif prod_sel == "-- Selecciona un Producto --":
            nombre_final_producto = ""

    with c2:
        cant = st.number_input("Cantidad", min_value=1, value=1)
    with c3:
        if "input_precio_key" not in st.session_state: st.session_state.input_precio_key = 0.0
        prec = st.number_input("Precio", key="input_precio_key", step=10.0)
    with c4:
        st.write("##")
        if st.button("➕ Agregar"):
            if nombre_final_producto:
                nuevo = pd.DataFrame([{"Descripción": nombre_final_producto, "Cantidad": cant, "Precio Unitario": prec}])
                st.session_state.factura_items = pd.concat([st.session_state.factura_items, nuevo], ignore_index=True)
                st.rerun()
            else:
                st.warning("Selecciona un producto.")

    # Tabla de items
    edited_df = st.data_editor(st.session_state.factura_items, num_rows="dynamic", use_container_width=True, key="editor_factura")
    st.session_state.factura_items = edited_df

    subtotal = 0
    if not st.session_state.factura_items.empty:
        st.session_state.factura_items['Total'] = st.session_state.factura_items['Cantidad'] * st.session_state.factura_items['Precio Unitario']
        subtotal = st.session_state.factura_items['Total'].sum()

    st.info(f"💰 Total a cobrar: {MONEDA} {subtotal:,.2f}")

    # --- 3. GENERAR PDF Y GUARDAR ---
    def generar_pdf():
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "VICMARAB COMERCIAL", ln=1, align="C")
        pdf.set_font("Arial", size=10)
        pdf.cell(0, 10, f"Cliente: {cliente_nombre} | Tel: {cliente_telefono}", ln=1)
        if cliente_direccion: pdf.cell(0, 5, f"Dirección: {cliente_direccion}", ln=1)
        pdf.cell(0, 5, f"Fecha: {fecha_factura}", ln=1)
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(100, 8, "Descripción", 1)
        pdf.cell(30, 8, "Cant.", 1)
        pdf.cell(30, 8, "Precio", 1)
        pdf.cell(30, 8, "Total", 1)
        pdf.ln()
        pdf.set_font("Arial", size=10)
        for _, row in st.session_state.factura_items.iterrows():
            pdf.cell(100, 8, str(row["Descripción"]), 1)
            pdf.cell(30, 8, str(row["Cantidad"]), 1)
            pdf.cell(30, 8, f"{row['Precio Unitario']:,.2f}", 1)
            pdf.cell(30, 8, f"{row['Total']:,.2f}", 1)
            pdf.ln()
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"TOTAL A PAGAR: {MONEDA} {subtotal:,.2f}", ln=1, align="R")
        return pdf.output(dest="S").encode("latin-1")

    if st.button("🖨️ Finalizar y Guardar Venta"):
        if cliente_nombre and not st.session_state.factura_items.empty:
            with st.spinner("Guardando en la nube..."):
                try:
                    df_ventas = cargar_datos_sheets("Ventas", ["Fecha", "Cliente", "Telefono", "Direccion", "Total"])
                    
                    nueva_venta = pd.DataFrame([{
                        "Fecha": str(fecha_factura),
                        "Cliente": cliente_nombre,
                        "Telefono": cliente_telefono,
                        "Direccion": cliente_direccion,
                        "Total": float(subtotal)
                    }])
                    
                    df_actualizado = pd.concat([df_ventas, nueva_venta], ignore_index=True)
                    conn.update(worksheet="Ventas", data=df_actualizado)
                    
                    # --- LIMPIEZA DE CACHÉ ---
                    st.cache_data.clear() # ¡CRUCIAL PARA VER EL CAMBIO!
                    
                    st.success("✅ Venta guardada.")
                    pdf_bytes = generar_pdf()
                    st.download_button("⬇️ Descargar PDF", data=pdf_bytes, file_name=f"Factura_{cliente_nombre}.pdf", mime="application/pdf")
                    st.session_state.factura_items = pd.DataFrame(columns=["Descripción", "Cantidad", "Precio Unitario"])
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            st.error("⚠️ Faltan datos.")

# ==============================================================================
# PESTAÑA 2: GASTOS
# ==============================================================================
with tab2:
    st.header("📉 Registro de Gastos")
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1: gasto_concepto = st.text_input("Concepto (Ej. Luz)")
    with col_g2: gasto_monto = st.number_input("Monto Gasto", min_value=0.0, step=100.0)
    with col_g3:
        gasto_fecha = st.date_input("Fecha Gasto", date.today())
        gasto_categoria = st.selectbox("Categoría", ["Materia Prima", "Transporte", "Servicios", "Nómina", "Otros"])

    if st.button("Guardar Gasto"):
        if gasto_concepto and gasto_monto > 0:
            with st.spinner("Guardando..."):
                try:
                    df_gastos = cargar_datos_sheets("Gastos", ["Fecha", "Concepto", "Categoría", "Monto"])
                    nuevo_gasto = pd.DataFrame([{
                        "Fecha": str(gasto_fecha), "Concepto": gasto_concepto,
                        "Categoría": gasto_categoria, "Monto": float(gasto_monto)
                    }])
                    conn.update(worksheet="Gastos", data=pd.concat([df_gastos, nuevo_gasto], ignore_index=True))
                    
                    # --- LIMPIEZA DE CACHÉ ---
                    st.cache_data.clear()
                    
                    st.success(f"✅ Gasto guardado.")
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            st.warning("Revisa los datos.")

# ==============================================================================
# PESTAÑA 3: ADMINISTRACIÓN
# ==============================================================================
with tab3:
    st.header("⚙️ Administración")
    if st.button("🔄 Recargar Datos Manualmente"):
        st.cache_data.clear()
        st.rerun()

    # --- RESUMEN ---
    df_v = cargar_datos_sheets("Ventas", ["Fecha", "Cliente", "Total"])
    df_g = cargar_datos_sheets("Gastos", ["Fecha", "Concepto", "Categoría", "Monto"])
    if not df_v.empty or not df_g.empty:
        ing = pd.to_numeric(df_v["Total"], errors='coerce').sum()
        gas = pd.to_numeric(df_g["Monto"], errors='coerce').sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos", f"{MONEDA} {ing:,.2f}")
        c2.metric("Gastos", f"{MONEDA} {gas:,.2f}")
        c3.metric("Ganancia", f"{MONEDA} {(ing-gas):,.2f}")
    st.divider()

    # --- AGREGAR PRODUCTO (FORMULARIO) ---
    st.subheader("📦 Agregar Producto Nuevo")
    with st.form("form_nuevo_prod", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        with c1: n_nom = st.text_input("Nombre")
        with c2: n_prec = st.number_input("Precio", min_value=0.0)
        if st.form_submit_button("➕ Guardar en Catálogo"):
            if n_nom:
                try:
                    df_cat = cargar_datos_sheets("Catalogo", ["Producto", "Precio"])
                    nuevo = pd.DataFrame([{"Producto": n_nom, "Precio": float(n_prec)}])
                    conn.update(worksheet="Catalogo", data=pd.concat([df_cat, nuevo], ignore_index=True))
                    st.cache_data.clear()
                    st.success(f"Producto '{n_nom}' agregado.")
                except Exception as e: st.error(f"Error: {e}")

    st.divider()

    # --- EDITAR TABLAS ---
    st.subheader("✏️ Editar Tablas (Borrados / Correcciones)")
    
    with st.expander("📂 Catálogo de Productos (Editar precios o borrar)", expanded=False):
        df_cat_edit = st.data_editor(cargar_datos_sheets("Catalogo", ["Producto", "Precio"]), num_rows="dynamic", use_container_width=True, key="ed_cat")
        if st.button("💾 Guardar Cambios Catálogo"):
            df_cat_edit["Precio"] = pd.to_numeric(df_cat_edit["Precio"], errors='coerce').fillna(0)
            conn.update(worksheet="Catalogo", data=df_cat_edit)
            st.cache_data.clear()
            st.success("Catálogo actualizado.")
            st.rerun()

    c_e1, c_e2 = st.columns(2)
    with c_e1:
        st.write("**Historial Ventas**")
        df_v_edit = st.data_editor(df_v, num_rows="dynamic", key="ed_vtas")
        if st.button("💾 Guardar Ventas"):
            conn.update(worksheet="Ventas", data=df_v_edit)
            st.cache_data.clear()
            st.success("Guardado.")
            st.rerun()
            
    with c_e2:
        st.write("**Historial Gastos**")
        # Creamos la tabla editable
        df_g_edit = st.data_editor(df_g, num_rows="dynamic", key="ed_gts")
        
        # Botón para guardar
        if st.button("💾 Guardar Gastos"):
            # IMPORTANTE: Todo lo que esté debajo del 'if' debe tener 4 espacios de sangría
            conn.update(worksheet="Gastos", data=df_g_edit)
            st.cache_data.clear()
            st.success("Guardado.")
            st.rerun()


