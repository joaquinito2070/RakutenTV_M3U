import os
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests
import gzip
from io import BytesIO
# Importaciones necesarias para el filtro de tiempo
from datetime import datetime, timezone, timedelta

# --- Fuentes de Datos ---
SOURCE_URL_W3U = "https://github.com/HelmerLuzo/RakutenTV_HL/raw/refs/heads/main/tv/w3u/RakutenTV_tv.w3u"
SOURCE_URL_EPG = "https://helmerluzo.github.io/RakutenTV_HL/epg/RakutenTV.xml.gz"

# --- URL EPG (la que tú has proporcionado) ---
EPG_FINAL_URL = "https://github.com/joaquinito2070/RakutenTV_M3U/raw/refs/heads/main/dist/rakuten_all.xml"

# --- Archivos de Salida ---
OUTPUT_DIR = "dist"
M3U_FILE = os.path.join(OUTPUT_DIR, "rakuten_all.m3u")
XML_FILE = os.path.join(OUTPUT_DIR, "rakuten_all.xml")
JSON_STATIONS_FILE = os.path.join(OUTPUT_DIR, "rakuten_all.json")
JSON_INDEX_FILE = os.path.join(OUTPUT_DIR, "index.json")


def get_data_from_source(url, is_gz=False):
    """Descarga datos. Si is_gz es True, descomprime el contenido."""
    print(f"Descargando datos desde: {url}")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Lanza error si la respuesta es 4xx o 5xx

        if is_gz:
            # Descomprimir .gz en memoria
            with gzip.GzipFile(fileobj=BytesIO(response.content)) as f:
                return f.read().decode('utf-8')
        else:
            # Devolver JSON
            return response.json()

    except requests.exceptions.RequestException as e:
        print(f"ERROR: No se pudo descargar {url}. {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"ERROR: El archivo de {url} no es un JSON válido. {e}")
        return None
    except (IOError, EOFError, gzip.BadGzipFile) as e:
        print(f"ERROR: No se pudo descomprimir el EPG de {url}. {e}")
        return None

# --- NUEVA FUNCIÓN AUXILIAR ---
def parse_xmltv_time(time_str):
    """Convierte un timestamp de XMLTV (ej: '20251116120000 +0000') a un objeto datetime."""
    try:
        # El formato es YYYYMMDDHHMMSS [+-]HHMM
        # strptime necesita que el offset no tenga espacio, ej: +0000
        if " " in time_str:
            parts = time_str.split(" ")
            time_str_fixed = parts[0] + parts[1]
            return datetime.strptime(time_str_fixed, '%Y%m%d%H%M%S%z')
        else:
            # Si no hay timezone, asumimos UTC (aunque es raro)
            return datetime.strptime(time_str, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    except Exception:
        # Si falla el parseo, devolvemos None para que sea filtrado
        return None


def generate_m3u(data):
    """Genera un único archivo M3U con la URL absoluta del EPG."""
    print(f"Generando {M3U_FILE}...")
    with open(M3U_FILE, "w", encoding="utf-8") as f:
        # Añadimos la URL absoluta del EPG en la cabecera
        f.write(f'#EXTM3U x-tvg-url="{EPG_FINAL_URL}"\n')

        for group in data.get("groups", []):
            group_title = group.get("name", "Sin Grupo")

            for station in group.get("stations", []):
                name = station.get("name")
                tvg_id = station.get("epgId")
                logo = station.get("image")
                stream_url = station.get("url")

                if not name or not stream_url or not tvg_id:
                    continue

                f.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" group-title="{group_title}",{name}\n')
                f.write(f'{stream_url}\n')


# --- FUNCIÓN MODIFICADA CON FILTRO DE TIEMPO ---
def generate_xmltv(channel_data, epg_xml_content):
    """
    Genera un archivo XMLTV filtrado solo con programas
    actuales y de las próximas 24 horas.
    """
    print(f"Generando {XML_FILE} (combinando canales y filtrando EPG)...")
    
    # 1. Definir el marco de tiempo
    now_utc = datetime.now(timezone.utc)
    limit_time_utc = now_utc + timedelta(days=1)
    
    # 2. Crear la base del nuevo archivo XMLTV
    tv_root = ET.Element("tv")
    tv_root.set("generator-info-name", "RakutenGenerator")

    channel_ids = set()
    programs_kept = 0
    programs_filtered = 0

    # 3. Añadir todos los elementos <channel> desde el .w3u
    for group in channel_data.get("groups", []):
        for station in group.get("stations", []):
            tvg_id = station.get("epgId")
            name = station.get("name")
            logo = station.get("image")

            if not tvg_id or tvg_id in channel_ids:
                continue
            
            channel_ids.add(tvg_id)
            ch_element = ET.SubElement(tv_root, "channel")
            ch_element.set("id", tvg_id)
            
            display_name = ET.SubElement(ch_element, "display-name")
            display_name.text = name
            
            if logo:
                icon = ET.SubElement(ch_element, "icon")
                icon.set("src", logo)
    
    # 4. Parsear el EPG descargado y AÑADIR SOLO LOS PROGRAMAS FILTRADOS
    try:
        epg_root = ET.fromstring(epg_xml_content)
        
        for program in epg_root.findall("programme"):
            start_str = program.get("start")
            stop_str = program.get("stop")
            
            # Si el programa no tiene horas, no podemos filtrarlo, lo descartamos
            if not start_str or not stop_str:
                programs_filtered += 1
                continue

            start_time = parse_xmltv_time(start_str)
            stop_time = parse_xmltv_time(stop_str)

            # Si las fechas son inválidas, lo descartamos
            if not start_time or not stop_time:
                programs_filtered += 1
                continue

            # --- ¡LA LÓGICA DE FILTRADO! ---
            # 1. El programa NO debe haber terminado (stop_time > now)
            # 2. El programa DEBE empezar antes del límite de 24h (start_time < limit_time)
            if stop_time > now_utc and start_time < limit_time_utc:
                tv_root.append(program) # Conservar este programa
                programs_kept += 1
            else:
                programs_filtered += 1 # Descartar este programa
            
    except ET.ParseError as e:
        print(f"ERROR: No se pudo parsear el XML del EPG. El EPG estará vacío. {e}")

    print(f"  -> Filtro de EPG: {programs_kept} programas conservados, {programs_filtered} programas descartados.")

    # 5. Guardar el archivo XML combinado y formateado
    try:
        xml_str = minidom.parseString(ET.tostring(tv_root)).toprettyxml(indent="  ", encoding="utf-8")
        with open(XML_FILE, "wb") as f:
            f.write(xml_str)
    except Exception as e:
        print(f"ERROR: No se pudo guardar el archivo XML. {e}")


def generate_json_output(data):
    """Genera un archivo JSON plano con la lista de estaciones."""
    print(f"Generando {JSON_STATIONS_FILE}...")
    data_list = []
    
    for group in data.get("groups", []):
        group_title = group.get("name", "Sin Grupo")
        for station in group.get("stations", []):
            flat_station = station.copy()
            flat_station["group_title"] = group_title
            data_list.append(flat_station)
    
    unique_data = {
        item.get('epgId', item.get('name')): item for item in data_list
    }.values()

    with open(JSON_STATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(unique_data), f, indent=2, ensure_ascii=False)


def generate_index_json():
    """Genera un archivo index.json con enlaces relativos y la URL absoluta del EPG."""
    print(f"Generando {JSON_INDEX_FILE}...")
    
    index_data = {
        "author": "RakutenTV M3U Generator",
        "last_updated": datetime.now().isoformat(),
        "files": {
            "m3u_url": os.path.basename(M3U_FILE),
            "epg_xml_url": EPG_FINAL_URL,
            "stations_json_url": os.path.basename(JSON_STATIONS_FILE)
        }
    }
    
    with open(JSON_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)


def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # 1. Descargar Canales (JSON) y EPG (XML)
    channel_data = get_data_from_source(SOURCE_URL_W3U)
    epg_xml_content = get_data_from_source(SOURCE_URL_EPG, is_gz=True)

    if not channel_data:
        print("ERROR FATAL: No se pudieron obtener los datos de los canales. Saliendo.")
        return

    if not epg_xml_content:
        print("ADVERTENCIA: No se pudo obtener el EPG. El archivo XMLTV solo contendrá canales.")

    # 2. Generar todos los archivos
    generate_m3u(channel_data)
    generate_json_output(channel_data)
    generate_xmltv(channel_data, epg_xml_content if epg_xml_content else "<tv></tv>") # Pasa un XML vacío si falla
    generate_index_json()
    
    print("\n¡Proceso completado!")


if __name__ == "__main__":
    main()
