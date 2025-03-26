import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import locale
import numpy as np
from datetime import datetime

# Configuración de locale para formatear números con separadores de miles
locale.setlocale(locale.LC_ALL, 'es_ES.UTF-8')

# Configuración de Google Sheets
def conectar_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", 
             "https://www.googleapis.com/auth/drive",
             "https://www.googleapis.com/auth/spreadsheets"]
    
    creds = ServiceAccountCredentials.from_json_keyfile_name("credenciales.json", scope)
    client = gspread.authorize(creds)
    
    # Conectar a todas las hojas necesarias
    spreadsheet = client.open("Presupuesto Hogar (Respuestas)")
    
    try:
        # Obtener datos de todas las hojas
        respuestas = pd.DataFrame(spreadsheet.worksheet("Respuestas de formulario 1").get_all_records())
        ppto_entrada = pd.DataFrame(spreadsheet.worksheet("Ppto Entrada").get_all_records())
        ppto_salida = pd.DataFrame(spreadsheet.worksheet("Ppto Salida").get_all_records())
        
        return {
            "respuestas": respuestas,
            "ppto_entrada": ppto_entrada,
            "ppto_salida": ppto_salida
        }
    except Exception as e:
        st.error(f"Error al obtener datos: {str(e)}")
        return None

# Función para formatear números con separadores de miles
def formatear_numero(valor):
    return locale.format_string("%d", valor, grouping=True)

# Función para mostrar tabla con agrupación por cuenta
def mostrar_tabla_agrupable(df, titulo, columna_valor="Valor"):
    st.header(f"📋 {titulo}")
    
    if not df.empty:
        # Limpieza y formateo de datos
        df[columna_valor] = pd.to_numeric(df[columna_valor], errors="coerce").fillna(0)
        
        # Mostrar opción para agrupar
        group_by_account = st.checkbox(f"Agrupar por cuenta", value=True, key=f"group_{titulo}")
        
        if group_by_account and "Cuenta" in df.columns:
            # Mostrar resumen por cuenta
            resumen_cuentas = df.groupby("Cuenta")[columna_valor].sum().reset_index()
            resumen_cuentas = resumen_cuentas.sort_values(by=columna_valor, ascending=False)
            
            # Mostrar tabla con estilo
            st.dataframe(
                resumen_cuentas.style.format({columna_valor: "${:,.0f}"}),
                width=800,
                height=300
            )
            
            # Mostrar detalles expandibles por cuenta
            st.subheader("Detalles por Cuenta")
            cuentas = df["Cuenta"].unique()
            for cuenta in cuentas:
                with st.expander(f"📌 {cuenta}"):
                    detalle_cuenta = df[df["Cuenta"] == cuenta]
                    st.dataframe(
                        detalle_cuenta.style.format({columna_valor: "${:,.0f}"}),
                        width=800,
                        height=200
                    )
        else:
            # Mostrar tabla completa sin agrupar
            st.dataframe(
                df.style.format({columna_valor: "${:,.0f}"}),
                width=800,
                height=300
            )
        
        # Mostrar total
        total = df[columna_valor].sum()
        st.metric(f"Total {titulo}", f"${formatear_numero(total)}")
    else:
        st.warning(f"No hay datos en {titulo}")

# Función para procesar y mostrar datos de ejecución
def mostrar_ejecucion_presupuesto(respuestas, ppto_entrada, ppto_salida):
    st.header("📊 Ejecución vs Presupuesto")
    
    # Procesar datos de respuestas (ejecución real)
    if not respuestas.empty:
        respuestas["Valor"] = pd.to_numeric(respuestas["Valor"], errors="coerce").fillna(0)
        respuestas["Fecha"] = pd.to_datetime(respuestas["Marca temporal"]).dt.date
        
        # Filtrar y procesar ingresos ejecutados
        ingresos_ejecutados = respuestas[respuestas["Tipo de movimiento"] == "Entrada"]
        ingresos_ejecutados = ingresos_ejecutados.groupby(["Cuenta", "Rubro", "Detalle"])["Valor"].sum().reset_index()
        ingresos_ejecutados.rename(columns={"Valor": "Ejecutado"}, inplace=True)
        
        # Filtrar y procesar gastos ejecutados
        gastos_ejecutados = respuestas[respuestas["Tipo de movimiento"] == "Salida"]
        gastos_ejecutados = gastos_ejecutados.groupby(["Cuenta", "Rubro", "Detalle"])["Valor"].sum().reset_index()
        gastos_ejecutados.rename(columns={"Valor": "Ejecutado"}, inplace=True)
    
    # Procesar presupuesto de entrada
    if not ppto_entrada.empty:
        ppto_entrada["Valor"] = pd.to_numeric(ppto_entrada["Valor"], errors="coerce").fillna(0)
        ppto_entrada.rename(columns={"Valor": "Presupuestado"}, inplace=True)
    
    # Procesar presupuesto de salida
    if not ppto_salida.empty:
        ppto_salida["Valor"] = pd.to_numeric(ppto_salida["Valor"], errors="coerce").fillna(0)
        ppto_salida.rename(columns={"Valor": "Presupuestado"}, inplace=True)
    
    # Cruce de información para ingresos
    if not ingresos_ejecutados.empty and not ppto_entrada.empty:
        ingresos_comparativo = pd.merge(
            ppto_entrada,
            ingresos_ejecutados,
            on=["Cuenta", "Rubro", "Detalle"],
            how="outer"
        ).fillna(0)
        
        # Calcular diferencia y porcentaje de ejecución
        ingresos_comparativo["Diferencia"] = ingresos_comparativo["Ejecutado"] - ingresos_comparativo["Presupuestado"]
        ingresos_comparativo["% Ejecución"] = (ingresos_comparativo["Ejecutado"] / ingresos_comparativo["Presupuestado"]) * 100
        ingresos_comparativo["% Ejecución"] = ingresos_comparativo["% Ejecución"].replace([np.inf, -np.inf], 0)
        
        st.subheader("Ingresos - Ejecución vs Presupuesto")
        st.dataframe(
            ingresos_comparativo.style.format({
                "Presupuestado": "${:,.0f}",
                "Ejecutado": "${:,.0f}",
                "Diferencia": "${:,.0f}",
                "% Ejecución": "{:.2f}%"
            }),
            width=1000,
            height=400
        )
    
    # Cruce de información para gastos
    if not gastos_ejecutados.empty and not ppto_salida.empty:
        gastos_comparativo = pd.merge(
            ppto_salida,
            gastos_ejecutados,
            on=["Cuenta", "Rubro", "Detalle"],
            how="outer"
        ).fillna(0)
        
        # Calcular diferencia y porcentaje de ejecución
        gastos_comparativo["Diferencia"] = gastos_comparativo["Ejecutado"] - gastos_comparativo["Presupuestado"]
        gastos_comparativo["% Ejecución"] = (gastos_comparativo["Ejecutado"] / gastos_comparativo["Presupuestado"]) * 100
        gastos_comparativo["% Ejecución"] = gastos_comparativo["% Ejecución"].replace([np.inf, -np.inf], 0)
        
        st.subheader("Gastos - Ejecución vs Presupuesto")
        st.dataframe(
            gastos_comparativo.style.format({
                "Presupuestado": "${:,.0f}",
                "Ejecutado": "${:,.0f}",
                "Diferencia": "${:,.0f}",
                "% Ejecución": "{:.2f}%"
            }),
            width=1000,
            height=400
        )

# Función principal
def main():
    st.set_page_config(page_title="HomeFinance", page_icon="💰", layout="wide")

    # Encabezado personalizado
    st.markdown(
        """
        <style>
        .header {
            background-color: #4CAF50;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            color: white;
            font-family: Arial, sans-serif;
        }
        .header h1 {
            font-size: 36px;
            margin: 0;
        }
        .header h3 {
            font-size: 24px;
            margin: 0;
        }
        .logo {
            width: 100px;
            margin-bottom: 10px;
        }
        </style>
        <div class="header">
            <img class="logo" src="https://cdn-icons-png.flaticon.com/512/3135/3135679.png" alt="Logo Finanzas">
            <h1>💰 HomeFinance</h1>
            <h3>Ejecución Presupuestaria</h3>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Cargar datos
    datos = conectar_google_sheets()
    if datos is None:
        st.error("No se pudieron cargar los datos. Verifica la conexión.")
        return

    # Mostrar presupuestos
    mostrar_tabla_agrupable(datos["ppto_entrada"], "Presupuesto de Entrada")
    mostrar_tabla_agrupable(datos["ppto_salida"], "Presupuesto de Salida")
    
    # Mostrar datos de ejecución
    st.markdown("<hr style='border: 1px solid #ddd;'>", unsafe_allow_html=True)
    st.header("📝 Ejecución Real (Respuestas de formulario 1)")
    
    if not datos["respuestas"].empty:
        # Limpieza de datos
        datos_respuestas = datos["respuestas"].copy()
        datos_respuestas["Valor"] = pd.to_numeric(datos_respuestas["Valor"], errors="coerce").fillna(0)
        datos_respuestas["Fecha"] = pd.to_datetime(datos_respuestas["Marca temporal"]).dt.date
        
        # Mostrar tabla completa
        st.dataframe(
            datos_respuestas.style.format({"Valor": "${:,.0f}"}),
            width=1000,
            height=400
        )
        
        # Resumen por tipo de movimiento
        st.subheader("Resumen por Tipo de Movimiento")
        resumen_movimientos = datos_respuestas.groupby("Tipo de movimiento")["Valor"].sum().reset_index()
        st.dataframe(
            resumen_movimientos.style.format({"Valor": "${:,.0f}"}),
            width=800,
            height=200
        )
    else:
        st.warning("No hay datos en las respuestas del formulario")
    
    # Mostrar comparativo presupuesto vs ejecución
    st.markdown("<hr style='border: 1px solid #ddd;'>", unsafe_allow_html=True)
    mostrar_ejecucion_presupuesto(datos["respuestas"], datos["ppto_entrada"], datos["ppto_salida"])

if __name__ == "__main__":
    main()