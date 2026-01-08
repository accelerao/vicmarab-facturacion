import streamlit as st
import pandas as pd
from datetime import date
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Sistema VICMARAB", layout="wide", page_icon="🛍️")
st.title("📊 VICMARAB - Sistema de Gestión en Nube")

MONEDA = "DOP"

# --- CONEXIÓN A GOOGLE SHEETS ---
# Busca la info en .streamlit/secrets.toml (Local) o en Secrets de Streamlit Cloud (Nube)
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNCIONES DE CARGA DE DATOS ---

def cargar_datos_sheets(hoja, columnas_esperadas):
    """Carga datos de Ventas o Gastos."""
    try:
        # ttl=0 para que no guarde caché y siempre muestre datos frescos
        df = conn.read(worksheet=hoja, ttl=0, usecols=columnas_esperadas)
        df = df.dropna(how="all")
        return df
    except Exception:
        # Si falla (hoja vacía), devuelve dataframe vacío
        return pd.DataFrame(columns=columnas_esperadas)

def obtener_catalogo():
    """Carga la lista de precios desde la pestaña 'Catalogo'."""
    try:
        # Leemos columnas A y B (Producto y Precio)
        df = conn.read(worksheet="Catalogo", ttl=0, usecols=[0, 1])
        df = df.dropna()
        
        # Si la hoja está vacía
        if df.empty:
            return {}
            
        # Convertimos a diccionario: {"Producto": Precio}
        # Asumimos que la columna 0 es el nombre y la 1 es el precio
        return dict(zip(df.iloc[:, 0], df.iloc[:, 1]))
    except Exception as e:
        st.error(f"Error cargando catálogo: {e}")
        return {}

# --- CARGAR CATÁLOGO AL INICIO ---
CATALOGO = obtener_catalogo()

if not CATALOGO:
    st.warning("⚠️ El catálogo parece vacío o no se pudo cargar. Revisa la pestaña 'Catalogo' en Google Sheets.")

# --- CREAMOS LAS PESTAÑAS ---
tab1, tab2, tab3 = st.tabs(["🧾 Facturación", "💸 Registrar Gastos", "📈 Contabilidad (Editar)"])

# ==============================================================================
# PESTAÑA 1: FACTURACIÓN
# ==============================================================================
with tab1:
    st.header("Nueva Factura")
    
    if 'factura_items' not in st.session_state:
        st.session_state.factura_items = pd.DataFrame(columns=["Descripción", "Cantidad", "Precio Unitario"])

    # --- 1. CARGAR HISTORIAL DE CLIENTES ---
    # Leemos ventas anteriores para obtener la base de datos de clientes
    df_clientes_db = cargar_datos_sheets("Ventas", ["Cliente", "Telefono", "Direccion"])
    
    # Obtenemos lista de nombres únicos (quitando vacíos)
    lista_clientes = []
    if not df_clientes_db.empty:
        # drop_duplicates: Si Juan compró 10 veces, solo tomamos la última vez
        df_unicos = df_clientes_db.drop_duplicates(subset=["Cliente"], keep="last")
        lista_clientes = df_unicos["Cliente"].dropna().tolist()
        lista_clientes.sort() # Ordenar alfabéticamente

    # --- 2. INTERFAZ DE SELECCIÓN ---
    with st.expander("👤 Datos del Cliente", expanded=True):
        # Buscador de clientes antiguos
        opcion_cliente = st.selectbox(
            "📂 Buscar Cliente Existente (o selecciona 'Nuevo')", 
            options=["-- Nuevo / Manual --"] + lista_clientes,
            index=0
        )

        # Lógica de autocompletado
        val_nombre = ""
        val_tel = ""
        val_dir = ""

        if opcion_cliente != "-- Nuevo / Manual --":
            # Si seleccionamos a alguien, buscamos sus datos
            datos = df_clientes_db[df_clientes_db["Cliente"] == opcion_cliente].iloc[-1]
            val_nombre = str(datos["Cliente"])
            # Usamos "get" por si la columna está vacía en excel
            val_tel = str(datos.get("Telefono", ""))
            val_dir = str(datos.get("Direccion", ""))
            
            # Limpieza de datos (quitar 'nan' si excel estaba sucio)
            if val_tel == "nan": val_tel = ""
            if val_dir == "nan": val_dir = ""

        col1, col2 = st.columns(2)
        with col1:
            # Usamos 'value' para pre-llenar si encontramos al cliente
            cliente_nombre = st.text_input("Nombre del Cliente", value=val_nombre, key="cli_nom")
            cliente_telefono = st.text_input("Número Telefónico", value=val_tel, key="cli_tel")
        with col2:
            fecha_factura = st.date_input("Fecha", date.today(), key="fecha_fac")
            cliente_direccion = st.text_input("Dirección de entrega", value=val_dir, key="cli_dir")

    st.divider()

    # --- (EL RESTO DEL CÓDIGO SIGUE IGUAL: PRODUCTOS, BOTÓN GUARDAR, ETC) ---
    # Solo asegúrate de que al GUARDAR (botón final), incluyas el teléfono en la hoja:
    
    # ... (Sección de productos igual que antes) ...

    # Copia esto también para asegurarnos de que el botón de guardar incluya el Teléfono
    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
    with c1:
        opciones = list(CATALOGO.keys()) if CATALOGO else ["Sin productos"]
        prod_sel = st.selectbox("Producto", options=opciones)
    with c2:
        cant = st.number_input("Cantidad", min_value=1, value=1)
    with c3:
        precio_sugerido = CATALOGO.get(prod_sel, 0.0)
        prec = st.number_input("Precio", value=float(precio_sugerido))
    with c4:
        st.write("##")
        if st.button("➕ Agregar"):
            if prod_sel != "Sin productos":
                nuevo = pd.DataFrame([{"Descripción": prod_sel, "Cantidad": cant, "Precio Unitario": prec}])
                st.session_state.factura_items = pd.concat([st.session_state.factura_items, nuevo], ignore_index=True)
                st.rerun()

    edited_df = st.data_editor(st.session_state.factura_items, num_rows="dynamic", use_container_width=True, key="editor_factura")
    st.session_state.factura_items = edited_df

    subtotal = 0
    total_final = 0
    if not st.session_state.factura_items.empty:
        st.session_state.factura_items['Total'] = st.session_state.factura_items['Cantidad'] * st.session_state.factura_items['Precio Unitario']
        subtotal = st.session_state.factura_items['Total'].sum()
        total_final = subtotal

    st.info(f"💰 Total a cobrar: {MONEDA} {total_final:,.2f}")

    def generar_pdf():
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "VICMARAB COMERCIAL", ln=1, align="C")
        pdf.set_font("Arial", size=10)
        pdf.cell(0, 10, f"Cliente: {cliente_nombre} | Tel: {cliente_telefono}", ln=1)
        if cliente_direccion:
            pdf.cell(0, 5, f"Dirección: {cliente_direccion}", ln=1)
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
        pdf.cell(0, 10, f"TOTAL A PAGAR: {MONEDA} {total_final:,.2f}", ln=1, align="R")
        return pdf.output(dest="S").encode("latin-1")

    if st.button("🖨️ Finalizar y Guardar Venta"):
        if cliente_nombre and not st.session_state.factura_items.empty:
            with st.spinner("Guardando en la nube..."):
                try:
                    # IMPORTANTE: Ahora cargamos y guardamos también el TELEFONO
                    df_ventas = cargar_datos_sheets("Ventas", ["Fecha", "Cliente", "Telefono", "Direccion", "Total"])
                    
                    nueva_venta = pd.DataFrame([{
                        "Fecha": str(fecha_factura),
                        "Cliente": cliente_nombre,
                        "Telefono": cliente_telefono,  # <-- Guardamos el teléfono para la próxima
                        "Direccion": cliente_direccion,
                        "Total": float(total_final)
                    }])
                    
                    df_actualizado = pd.concat([df_ventas, nueva_venta], ignore_index=True)
                    conn.update(worksheet="Ventas", data=df_actualizado)
                    
                    st.success("✅ Venta guardada.")
                    pdf_bytes = generar_pdf()
                    st.download_button("⬇️ Descargar PDF", data=pdf_bytes, file_name=f"Factura_{cliente_nombre}.pdf", mime="application/pdf")
                    st.session_state.factura_items = pd.DataFrame(columns=["Descripción", "Cantidad", "Precio Unitario"])
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            st.error("⚠️ Faltan datos.")
# ==============================================================================
# PESTAÑA 2: REGISTRAR GASTOS
# ==============================================================================
with tab2:
    st.header("📉 Registro de Gastos")
    
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        gasto_concepto = st.text_input("Concepto (Ej. Luz, Agua)")
    with col_g2:
        gasto_monto = st.number_input("Monto Gasto", min_value=0.0, step=100.0)
    with col_g3:
        gasto_fecha = st.date_input("Fecha Gasto", date.today())
        gasto_categoria = st.selectbox("Categoría", ["Materia Prima", "Transporte", "Servicios", "Nómina", "Otros"])

    if st.button("Guardar Gasto"):
        if gasto_concepto and gasto_monto > 0:
            with st.spinner("Guardando gasto..."):
                try:
                    df_gastos = cargar_datos_sheets("Gastos", ["Fecha", "Concepto", "Categoría", "Monto"])
                    
                    nuevo_gasto = pd.DataFrame([{
                        "Fecha": str(gasto_fecha),
                        "Concepto": gasto_concepto,
                        "Categoría": gasto_categoria,
                        "Monto": float(gasto_monto)
                    }])
                    
                    df_gastos_actualizado = pd.concat([df_gastos, nuevo_gasto], ignore_index=True)
                    conn.update(worksheet="Gastos", data=df_gastos_actualizado)
                    
                    st.success(f"✅ Gasto de {MONEDA} {gasto_monto} guardado.")
                except Exception as e:
                    st.error(f"Error al guardar: {e}")
        else:
            st.warning("Revisa el concepto o el monto.")

# ==============================================================================
# PESTAÑA 3: CONTABILIDAD Y GESTIÓN DE PRODUCTOS
# ==============================================================================
with tab3:
    st.header("⚙️ Administración del Negocio")
    st.info("💡 Aquí puedes editar el historial y gestionar tus productos. Los cambios se guardan en la Nube.")
    
    # Botón de emergencia para recargar si algo no cuadra
    if st.button("🔄 Forzar Recarga de Datos"):
        st.cache_data.clear()
        st.rerun()

    # --- 1. SECCIÓN DE FINANZAS ---
    df_v = cargar_datos_sheets("Ventas", ["Fecha", "Cliente", "Total"])
    df_g = cargar_datos_sheets("Gastos", ["Fecha", "Concepto", "Categoría", "Monto"])

    if not df_v.empty or not df_g.empty:
        total_ingresos = pd.to_numeric(df_v["Total"], errors='coerce').sum()
        total_gastos = pd.to_numeric(df_g["Monto"], errors='coerce').sum()
        ganancia_neta = total_ingresos - total_gastos

        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos Totales", f"{MONEDA} {total_ingresos:,.2f}")
        c2.metric("Gastos Totales", f"{MONEDA} {total_gastos:,.2f}")
        c3.metric("Ganancia Neta", f"{MONEDA} {ganancia_neta:,.2f}")
    
    st.divider()

    # --- 2. GESTIÓN DE PRODUCTOS ---
    st.subheader("📦 Catálogo de Productos")
    st.caption("Añade productos abajo o modifica los precios existentes.")
    
    # Carga Catalogo
    df_catalogo = cargar_datos_sheets("Catalogo", ["Producto", "Precio"])
    
    # Editor de Productos
    df_catalogo_editado = st.data_editor(
        df_catalogo,
        num_rows="dynamic", # Permite añadir filas nuevas
        use_container_width=True,
        key="editor_catalogo_main",
        column_config={
            "Precio": st.column_config.NumberColumn(
                "Precio Unitario",
                format="$%d", # Formato de dinero
                min_value=0,
                step=5
            )
        }
    )

    if st.button("💾 Guardar Cambios en Catálogo"):
        try:
            # Validacion numerica
            df_catalogo_editado["Precio"] = pd.to_numeric(df_catalogo_editado["Precio"], errors='coerce').fillna(0)
            
            # Guardar
            conn.update(worksheet="Catalogo", data=df_catalogo_editado)
            
            st.success("✅ Catálogo actualizado. Los vendedores verán los nuevos precios.")
            st.cache_data.clear() # Limpiamos memoria para que se actualice la lista en la Pestaña 1
            st.rerun() # Reiniciamos la app
        except Exception as e:
            st.error(f"Error al guardar catálogo: {e}")

    st.divider()

    # --- 3. HISTORIAL DE VENTAS Y GASTOS ---
    col_edit1, col_edit2 = st.columns(2)
    
    with col_edit1:
        st.subheader("📝 Historial Ventas")
        df_ventas_editado = st.data_editor(df_v, num_rows="dynamic", use_container_width=True, key="ed_vtas")
        if st.button("💾 Guardar Ventas"):
            conn.update(worksheet="Ventas", data=df_ventas_editado)
            st.success("Guardado.")
            st.rerun()

    with col_edit2:
        st.subheader("📝 Historial Gastos")
        df_gastos_editado = st.data_editor(df_g, num_rows="dynamic", use_container_width=True, key="ed_gts")
        if st.button("💾 Guardar Gastos"):
            conn.update(worksheet="Gastos", data=df_gastos_editado)
            st.success("Guardado.")
            st.rerun()
