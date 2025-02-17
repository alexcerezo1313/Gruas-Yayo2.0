import streamlit as st
import json
import pandas as pd

# --------------------------------------------------------------------
# Mostrar el logo en la parte superior del Sidebar
st.sidebar.image("logo.png", width=200)

st.title("Selector de Grúas Torre")
st.sidebar.header("Filtros de búsqueda")

# --------------------------------------------------------------------
# Cargar datos desde JSON
@st.cache_data
def load_data(json_file):
    with open(json_file, "r", encoding="utf-8") as f:
        return json.load(f)

data = load_data("gruas_data.json")
gruas_list = data.get("Hoja1", [])

# Función auxiliar (aquí no se utiliza para filtrar, pero se deja por posibles futuras necesidades)
def base_model(model_str):
    if model_str:
        return model_str.split("/")[0].strip()
    return ""

# --------------------------------------------------------------------
# Parámetros obligatorios
target_alcance = st.sidebar.number_input("(A) Alcance Deseado (m):", value=30.0, step=0.5)
target_carga_punta = st.sidebar.number_input("(B) Carga en Punta (kg):", value=1000, step=100)

# Para "Pluma Instalada": se aceptan grúas con valor entre target y target*1.15
alcance_min = float(target_alcance)
alcance_max = target_alcance * 1.15

# Para "Carga en Punta": se aceptan grúas con valor entre target y target*1.20
carga_punta_min = float(target_carga_punta)
carga_punta_max = target_carga_punta * 1.20

# --------------------------------------------------------------------
# Parámetros opcionales para Carga Intermedia Deseada
use_intermedia = st.sidebar.checkbox("Carga Intermedia Deseada")
if use_intermedia:
    target_distancia = st.sidebar.number_input("(C) Distancia Deseada (m):", value=14.0, step=0.5)
    target_carga_intermedia = st.sidebar.number_input("(D) Carga Intermedia Deseada (kg):", value=2420, step=100)
    # Se exigen valores entre target y target*1.05 (±5%) para estos parámetros
    distancia_min = float(target_distancia)
    distancia_max = target_distancia * 1.05
    carga_intermedia_min = float(target_carga_intermedia)
    carga_intermedia_max = target_carga_intermedia * 1.05

# --------------------------------------------------------------------
# Función para calcular el error relativo (asumiendo que el valor >= target)
def relative_error(value, target):
    return (value - target) / target

# --------------------------------------------------------------------
# Filtrado y clasificación de candidatos (SIN opción de stock)
candidatos = []

for grua in gruas_list:
    try:
        alcance_val = float(grua.get("Pluma Instalada", 0))
        carga_val = float(grua.get("Carga en Punta", 0))
    except:
        continue

    # Filtrar: rechazar si el valor está por debajo del target o supera el máximo permitido.
    if not (alcance_min <= alcance_val <= alcance_max):
        continue
    if not (carga_punta_min <= carga_val <= carga_punta_max):
        continue

    # Calcular errores relativos para alcance y carga en punta
    err_alcance = relative_error(alcance_val, target_alcance)
    err_carga = relative_error(carga_val, target_carga_punta)
    # Descarta si alguno supera el 15%
    if err_alcance > 0.15 or err_carga > 0.15:
        continue
    total_error = err_alcance + err_carga

    if use_intermedia:
        try:
            dist_val = float(grua.get("Distancia Específica", 0))
            carga_int_val = float(grua.get("Carga específica", 0))
        except:
            continue
        if not (distancia_min <= dist_val <= distancia_max):
            continue
        if not (carga_intermedia_min <= carga_int_val <= carga_intermedia_max):
            continue
        err_dist = relative_error(dist_val, target_distancia)
        err_carga_int = relative_error(carga_int_val, target_carga_intermedia)
        if err_dist > 0.15 or err_carga_int > 0.15:
            continue
        total_error += (err_dist + err_carga_int)
        grua["_errors"] = {"Alcance": err_alcance, "Carga en Punta": err_carga,
                           "Distancia": err_dist, "Carga Intermedia": err_carga_int}
    else:
        grua["_errors"] = {"Alcance": err_alcance, "Carga en Punta": err_carga}
    grua["Total Error"] = total_error

    # Asignar un "Tipo" para efectos de estilo:
    # Si ambos errores (alcance y carga) son ≤ 5% se marca "Match" (verde); de lo contrario, "Casi Match" (amarillo)
    if err_alcance <= 0.05 and err_carga <= 0.05:
        grua["Tipo"] = "Match"
    else:
        grua["Tipo"] = "Casi Match"
    candidatos.append(grua)

# Ordenar candidatos de menor a mayor Total Error
candidatos = sorted(candidatos, key=lambda x: x["Total Error"])

# Eliminar duplicados (por ejemplo, si el mismo modelo aparece varias veces, conservar el de menor error)
candidatos_unicos = {}
for cand in candidatos:
    modelo = cand.get("Modelo de Grúa Torre", "")
    if modelo not in candidatos_unicos:
        candidatos_unicos[modelo] = cand
    else:
        if cand["Total Error"] < candidatos_unicos[modelo]["Total Error"]:
            candidatos_unicos[modelo] = cand

candidatos_filtrados = list(candidatos_unicos.values())
resultados = candidatos_filtrados[:5]

# --------------------------------------------------------------------
# Preparar la tabla de resultados y la imagen debajo de la tabla
if not resultados:
    st.write("No se encontraron grúas que se ajusten a los parámetros solicitados.")
else:
    # Definir las columnas a mostrar:
    # Siempre se muestran: Modelo, Pluma Instalada y Carga en Punta.
    columnas = ["Modelo de Grúa Torre", "Pluma Instalada (m)", "Carga en Punta (kg)"]
    if use_intermedia:
        columnas += ["Distancia Específica (m)", "Carga específica (kg)"]
    # Además, internamente guardamos "Total Error" y "Tipo" para el estilo, pero se ocultarán.
    cols_aux = ["Total Error", "Tipo"]

    # Función para formatear cada fila
    def formatea_fila(grua):
        fila = {}
        fila["Modelo de Grúa Torre"] = grua.get("Modelo de Grúa Torre", "")
        fila["Pluma Instalada (m)"] = f"{float(grua.get('Pluma Instalada', 0)):.2f}"
        fila["Carga en Punta (kg)"] = f"{int(round(float(grua.get('Carga en Punta', 0)))):,d}"
        if use_intermedia:
            fila["Distancia Específica (m)"] = f"{float(grua.get('Distancia Específica', 0)):.2f}"
            fila["Carga específica (kg)"] = f"{int(round(float(grua.get('Carga específica', 0)))):,d}"
        fila["Total Error"] = f"{grua.get('Total Error', 0):.3f}"
        fila["Tipo"] = grua.get("Tipo", "")
        return fila

    df = pd.DataFrame([formatea_fila(g) for g in resultados])
    columnas_final = columnas + cols_aux
    df = df[columnas_final]
    
    # Función para colorear filas según el "Tipo"
    def color_rows(row):
        if row["Tipo"] == "Match":
            return ['background-color: lightgreen'] * len(row)
        elif row["Tipo"] == "Casi Match":
            return ['background-color: lightyellow'] * len(row)
        else:
            return [''] * len(row)
    
    styled_df = df.style.apply(color_rows, axis=1)
    
    # Ocultar las columnas auxiliares "Total Error" y "Tipo" mediante CSS
    hide_styles = []
    for col in cols_aux:
        if col in df.columns:
            col_index = list(df.columns).index(col)
            hide_styles.append({
                'selector': f'th.col{col_index}',
                'props': [('display', 'none')]
            })
            hide_styles.append({
                'selector': f'td.col{col_index}',
                'props': [('display', 'none')]
            })
    styled_df = styled_df.set_table_styles(hide_styles, overwrite=False)
    
    st.header("Opciones encontradas")
    st.dataframe(styled_df)
    
    # Mostrar la imagen debajo de la tabla con un tamaño mayor (por ejemplo, width=400)
    st.image("a.png", width=400)
