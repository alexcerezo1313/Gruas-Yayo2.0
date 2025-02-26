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

# Función auxiliar para extraer la parte del modelo antes de "/" (o paréntesis)
def trim_model(model_str):
    if "/" in model_str:
        return model_str.split("/")[0].strip()
    else:
        return model_str.strip()

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
# Nueva opción: Inventario
use_inventario = st.sidebar.checkbox("Inventario")
inventario_dict = {}
if use_inventario:
    unique_models = sorted({ trim_model(grua.get("Modelo de Grúa Torre", "")) 
                             for grua in gruas_list if grua.get("Modelo de Grúa Torre", "") })
    st.sidebar.subheader("Inventario")
    for modelo in unique_models:
        inventario_dict[modelo] = st.sidebar.number_input(f"Inventario para {modelo}:", value=0, step=1)

# --------------------------------------------------------------------
# Función para calcular el error relativo (asumiendo que el valor >= target)
def relative_error(value, target):
    return (value - target) / target

# --------------------------------------------------------------------
# Filtrado y clasificación de candidatos (que cumplan los requisitos)
candidatos = []
for grua in gruas_list:
    try:
        alcance_val = float(grua.get("Pluma Instalada", 0))
        carga_val = float(grua.get("Carga en Punta", 0))
    except:
        continue

    # Se requiere que ambos campos estén dentro del rango permitido
    if not (alcance_min <= alcance_val <= alcance_max):
        continue
    if not (carga_punta_min <= carga_val <= carga_punta_max):
        continue

    err_alcance = relative_error(alcance_val, target_alcance)
    err_carga = relative_error(carga_val, target_carga_punta)
    # Se descarta si alguno supera el 15%
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

    if err_alcance <= 0.05 and err_carga <= 0.05:
        grua["Tipo"] = "Match"
    else:
        grua["Tipo"] = "Casi Match"
    candidatos.append(grua)

# Ordenar candidatos y eliminar duplicados (se conserva el de menor error para cada modelo)
candidatos = sorted(candidatos, key=lambda x: x["Total Error"])
candidatos_unicos = {}
for cand in candidatos:
    modelo = cand.get("Modelo de Grúa Torre", "")
    modelo_trim = trim_model(modelo)
    if modelo_trim not in candidatos_unicos:
        candidatos_unicos[modelo_trim] = cand
    else:
        if cand["Total Error"] < candidatos_unicos[modelo_trim]["Total Error"]:
            candidatos_unicos[modelo_trim] = cand

candidatos_filtrados = list(candidatos_unicos.values())
resultados = candidatos_filtrados[:5]

# --------------------------------------------------------------------
# Si no se encontraron candidatos que cumplan los requisitos,
# se buscan dos grúas aproximadas:
#   - Una en la que BOTH "Pluma Instalada" y "Carga en Punta" sean menores al target.
#   - Otra en la que ambas sean mayores.
if not resultados:
    aproximado_menor = None  # Ambas medidas menores
    aproximado_mayor = None  # Ambas medidas mayores
    best_error_neg = -float('inf')  # Entre los candidatos con ambos campos menores, buscamos el que esté más cerca de 0 (error negativo mayor)
    best_error_pos = float('inf')    # Para los que tienen ambos campos mayores, buscamos el que esté más cerca de 0 (error positivo menor)
    
    for grua in gruas_list:
        try:
            alcance_val = float(grua.get("Pluma Instalada", 0))
            carga_val = float(grua.get("Carga en Punta", 0))
        except:
            continue
        
        # Solo consideramos candidatos en los que AMBOS campos sean menores al target:
        if alcance_val < target_alcance and carga_val < target_carga_punta:
            err_alcance = relative_error(alcance_val, target_alcance)
            err_carga = relative_error(carga_val, target_carga_punta)
            total_error = err_alcance + err_carga  # será negativo
            if total_error > best_error_neg:
                best_error_neg = total_error
                aproximado_menor = grua.copy()
                aproximado_menor["Total Error"] = total_error
        # O candidatos en los que AMBOS campos sean mayores al target:
        elif alcance_val > target_alcance and carga_val > target_carga_punta:
            err_alcance = relative_error(alcance_val, target_alcance)
            err_carga = relative_error(carga_val, target_carga_punta)
            total_error = err_alcance + err_carga  # será positivo
            if total_error < best_error_pos:
                best_error_pos = total_error
                aproximado_mayor = grua.copy()
                aproximado_mayor["Total Error"] = total_error

    resultados = []
    if aproximado_menor is not None:
        aproximado_menor["Tipo"] = "Aproximado"
        aproximado_menor["Aproximado"] = True
        resultados.append(aproximado_menor)
    if aproximado_mayor is not None:
        aproximado_mayor["Tipo"] = "Aproximado"
        aproximado_mayor["Aproximado"] = True
        resultados.append(aproximado_mayor)

# --------------------------------------------------------------------
# Si se habilita Inventario, se añade esa información a cada candidato
if use_inventario:
    for grua in resultados:
        modelo = grua.get("Modelo de Grúa Torre", "")
        modelo_trim = trim_model(modelo)
        disponible = inventario_dict.get(modelo_trim, 0)
        if disponible > 0:
            grua["Inventario"] = disponible
        else:
            grua["Inventario"] = "No hay"

# --------------------------------------------------------------------
# Preparar la tabla de resultados y mostrar la imagen debajo
columnas = ["Modelo de Grúa Torre", "Pluma Instalada (m)", "Carga en Punta (kg)"]
if use_intermedia:
    columnas += ["Distancia Específica (m)", "Carga específica (kg)"]
if use_inventario:
    columnas.append("Inventario")
cols_aux = ["Total Error", "Tipo"]

def formatea_fila(grua):
    fila = {}
    fila["Modelo de Grúa Torre"] = grua.get("Modelo de Grúa Torre", "")
    fila["Pluma Instalada (m)"] = f"{float(grua.get('Pluma Instalada', 0)):.2f}"
    fila["Carga en Punta (kg)"] = f"{int(round(float(grua.get('Carga en Punta', 0)))):,d}"
    if use_intermedia:
        fila["Distancia Específica (m)"] = f"{float(grua.get('Distancia Específica', 0)):.2f}"
        fila["Carga específica (kg)"] = f"{int(round(float(grua.get('Carga específica', 0)))):,d}"
    if use_inventario:
        fila["Inventario"] = grua.get("Inventario", "")
    fila["Total Error"] = f"{grua.get('Total Error', 0):.3f}"
    fila["Tipo"] = grua.get("Tipo", "")
    fila["Aproximado"] = grua.get("Aproximado", False)
    return fila

df = pd.DataFrame([formatea_fila(g) for g in resultados])
columnas_final = columnas + cols_aux + ["Aproximado"]
df = df[columnas_final]

def color_rows(row):
    # Si es una grúa aproximada, se pinta en naranja
    if row.get("Aproximado", False):
        return ['background-color: orange'] * len(row)
    # Si no hay inventario, se pinta en rojo
    elif "Inventario" in row and row["Inventario"] == "No hay":
        return ['background-color: red'] * len(row)
    else:
        if row["Tipo"] == "Match":
            return ['background-color: lightgreen'] * len(row)
        elif row["Tipo"] == "Casi Match":
            return ['background-color: #ffcc00'] * len(row)
        else:
            return [''] * len(row)

styled_df = df.style.apply(color_rows, axis=1)

hide_styles = []
for col in cols_aux + ["Aproximado"]:
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

st.image("a.png", width=400)
