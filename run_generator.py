import os
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests
import gzip
from io import BytesIO
from datetime import datetime, timezone, timedelta # Importaciones de tiempo

# --- Fuentes de Datos ---
SOURCE_URL_W3U = "https://github.com/HelmerLuzo/RakutenTV_HL/raw/refs/heads/main/tv/w3u/RakutenTV_tv.w3u"
SOURCE_URL_EPG = "https://helmerluzo.github.io/RakutenTV_HL/epg/RakutenTV.xml.gz"

# --- URL Finales Absolutas (las que tú has proporcionado) ---
M3U_FINAL_URL = "https://github.com/joaquinito2070/RakutenTV_M3U/raw/refs/heads/main/dist/rakuten_all.m3u"
JSON_FINAL_URL = "https://github.com/joaquinito2070/RakutenTV_M3U/raw/refs/heads/main/dist/rakuten_all.json"
EPG_FINAL_URL = "https://github.com/joaquinito2070/RakutenTV_M3U/raw/refs/heads/main/dist/rakuten_all.xml"

# --- Archivos de Salida (Locales) ---
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
        response.raise_for_status()

        if is_gz:
            with gzip.GzipFile(fileobj=BytesIO(response.content)) as f:
                return f.read().decode('utf-8')
        else:
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


def parse_xmltv_time(time_str):
    """Convierte un timestamp de XMLTV a un objeto datetime."""
    try:
        if " " in time_str:
            parts = time_str.split(" ")
            time_str_fixed = parts[0] + parts[1]
            return datetime.strptime(time_str_fixed, '%Y%m%d%H%M%S%z')
        else:
            return datetime.strptime(time_str, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    except Exception:
        return None


def get_filtered_programs(epg_root, hours_limit):
    """
    Devuelve una lista de elementos <programme> que están dentro 
    del marco de tiempo especificado.
    """
    programs_list = []
    programs_kept = 0
    programs_filtered = 0
    
    now_utc = datetime.now(timezone.utc)
    limit_time_utc = now_utc + timedelta(hours=hours_limit)
    
    if epg_root is None:
        return []

    for program in epg_root.findall("programme"):
        start_str = program.get("start")
        stop_str = program.get("stop")
        
        if not start_str or not stop_str:
            programs_filtered += 1
            continue

        start_time = parse_xmltv_time(start_str)
        stop_time = parse_xmltv_time(stop_str)

        if not start_time or not stop_time:
            programs_filtered += 1
            continue

        if stop_time > now_utc and start_time < limit_time_utc:
            programs_list.append(program)
            programs_kept += 1
        else:
            programs_filtered += 1
    
    print(f"  -> Filtro de {hours_limit}h: {programs_kept} programas conservados, {programs_filtered} programas descartados.")
    return programs_list


def generate_m3u(data):
    """Genera un único archivo M3U con la URL absoluta del EPG."""
    print(f"Generando {M3U_FILE}...")
    with open(M3U_FILE, "w", encoding="utf-8") as f:
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


def generate_xmltv(channel_data, filtered_programs_24h):
    """
    Genera un archivo XMLTV (24h) combinando canales
    y la lista de programas ya filtrada.
    """
    print(f"Generando {XML_FILE}...")
    
    tv_root = ET.Element("tv")
    tv_root.set("generator-info-name", "RakutenGenerator")

    channel_ids = set()

    # 1. Añadir todos los elementos <channel>
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
    
    # 2. Añadir los programas de 24h (ya filtrados)
    for program in filtered_programs_24h:
        tv_root.append(program)

    # 3. Guardar el archivo XML
    try:
        xml_str = minidom.parseString(ET.tostring(tv_root)).toprettyxml(indent="  ", encoding="utf-8")
        with open(XML_FILE, "wb") as f:
            f.write(xml_str)
    except Exception as e:
        print(f"ERROR: No se pudo guardar el archivo XML. {e}")


def generate_stations_json(channel_data, filtered_programs_12h):
    """
    Genera un archivo JSON con la lista de estaciones,
    incluyendo el EPG de 12h integrado y la URL del EPG.
    """
    print(f"Generando {JSON_STATIONS_FILE} (con EPG de 12h integrado)...")
    
    # 1. Crear un mapa de programas (channel_id -> [lista de programas])
    program_map = {}
    for program in filtered_programs_12h:
        channel_id = program.get("channel")
        if not channel_id:
            continue
        
        program_dict = {
            "start": program.get("start"),
            "stop": program.get("stop"),
            "title": program.findtext("title"),
            "desc": program.findtext("desc")
        }
        
        if channel_id not in program_map:
            program_map[channel_id] = []
        program_map[channel_id].append(program_dict)

    # 2. Construir la lista de estaciones
    station_list = []
    channel_ids_seen = set()
    
    for group in channel_data.get("groups", []):
        group_title = group.get("name", "Sin Grupo")
        for station in group.get("stations", []):
            tvg_id = station.get("epgId")
            
            if not tvg_id or tvg_id in channel_ids_seen:
                continue
            channel_ids_seen.add(tvg_id)
            
            flat_station = station.copy()
            flat_station["group_title"] = group_title
            flat_station["epg"] = program_map.get(tvg_id, [])
            station_list.append(flat_station)
    
    # 3. Crear el objeto JSON final
    final_json_data = {
        "epg_xmltv_url": EPG_FINAL_URL,
        "stations": station_list
    }

    # 4. Guardar el archivo JSON
    with open(JSON_STATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(final_json_data, f, indent=2, ensure_ascii=False)


# --- FUNCIÓN MODIFICADA ---
def generate_index_json():
    """Genera un archivo index.json con enlaces absolutos a los archivos generados."""
    print(f"Generando {JSON_INDEX_FILE}...")
    
    index_data = {
        "author": "RakutenTV M3U Generator",
        "last_updated": datetime.now().isoformat(),
        "files": {
            "m3u_url": M3U_FINAL_URL,             # <-- CAMBIO
            "epg_xml_url": EPG_FINAL_URL,
            "stations_json_url": JSON_FINAL_URL   # <-- CAMBIO
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

    epg_root = None
    if epg_xml_content:
        try:
            epg_root = ET.fromstring(epg_xml_content)
        except ET.ParseError as e:
            print(f"ERROR: No se pudo parsear el XML del EPG. {e}")
    else:
        print("ADVERTENCIA: No se pudo obtener el EPG.")

    if epg_root is None:
        epg_root = ET.Element("tv") 

    # 2. Filtrar programas para AMBAS duraciones
    print("Filtrando EPG...")
    programs_for_xml_24h = get_filtered_programs(epg_root, 24)
    programs_for_json_12h = get_filtered_programs(epg_root, 12)
    
    # 3. Generar todos los archivos
    generate_m3u(channel_data)
    generate_xmltv(channel_data, programs_for_xml_24h)
    generate_stations_json(channel_data, programs_for_json_12h)
    generate_index_json()
    
    print("\n¡Proceso completado!")


if __name__ == "__main__":
    main()
