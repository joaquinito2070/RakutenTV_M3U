import os
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests

# URL de la fuente de datos (el archivo .w3u que especificaste)
SOURCE_URL = "https://github.com/HelmerLuzo/RakutenTV_HL/raw/refs/heads/main/tv/w3u/RakutenTV_tv.w3u"

# Directorio para guardar los archivos generados
OUTPUT_DIR = "dist"


def get_data_from_source():
    """Descarga y parsea el JSON principal desde la URL."""
    print(f"Descargando datos desde {SOURCE_URL}...")
    try:
        response = requests.get(SOURCE_URL, timeout=10)
        response.raise_for_status() # Lanza error si la respuesta es 4xx o 5xx
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"ERROR: No se pudo descargar el archivo JSON de {SOURCE_URL}")
        print(e)
        return None
    except json.JSONDecodeError as e:
        print(f"ERROR: El archivo de {SOURCE_URL} no es un JSON válido.")
        print(e)
        return None


def generate_m3u(data):
    """Genera un único archivo rakuten_all.m3u"""
    filename = os.path.join(OUTPUT_DIR, "rakuten_all.m3u")
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        
        # Iteramos sobre la estructura del JSON "groups" -> "stations"
        for group in data.get("groups", []):
            group_title = group.get("name", "Sin Grupo")
            
            for station in group.get("stations", []):
                name = station.get("name")
                # Usamos epgId (del JSON) como el tvg-id
                tvg_id = station.get("epgId")
                logo = station.get("image")
                stream_url = station.get("url")
                
                # Omitimos si falta información esencial
                if not name or not stream_url or not tvg_id:
                    continue
                    
                f.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" group-title="{group_title}",{name}\n')
                f.write(f'{stream_url}\n')
    
    print(f"  -> Generado: {filename}")


def generate_xmltv(data):
    """Genera un único archivo rakuten_all.xml (solo canales, sin programación)"""
    filename = os.path.join(OUTPUT_DIR, "rakuten_all.xml")
    
    # Raíz del documento XMLTV
    tv_root = ET.Element("tv")
    tv_root.set("generator-info-name", "RakutenGenerator")

    channel_ids = set() # Para evitar duplicados

    for group in data.get("groups", []):
        for station in group.get("stations", []):
            tvg_id = station.get("epgId")
            name = station.get("name")
            logo = station.get("image")
            
            # Omitimos si no hay ID o si ya lo añadimos
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

    # Convertir a string con formato "bonito" (pretty-print)
    xml_str = minidom.parseString(ET.tostring(tv_root)).toprettyxml(indent="  ", encoding="utf-8")
    
    with open(filename, "wb") as f:
        f.write(xml_str)
        
    print(f"  -> Generado: {filename}")


def generate_json_output(data):
    """Genera un archivo JSON simple (rakuten_all.json) con los datos aplanados."""
    filename = os.path.join(OUTPUT_DIR, "rakuten_all.json")
    data_list = []
    
    for group in data.get("groups", []):
        group_title = group.get("name", "Sin Grupo")
        for station in group.get("stations", []):
            # Creamos un dict plano y le añadimos el grupo
            flat_station = station.copy()
            flat_station["group_title"] = group_title
            data_list.append(flat_station)
    
    # Eliminamos duplicados basados en 'epgId'
    # Usamos epgId si existe, si no el nombre, como clave única
    unique_data = {
        item.get('epgId', item.get('name')): item for item in data_list
    }.values()

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(list(unique_data), f, indent=2, ensure_ascii=False)
        
    print(f"  -> Generado: {filename}")


def main():
    # Creamos el directorio de salida si no existe
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # 1. Descargar los datos
    data = get_data_from_source()
    
    if data:
        print("Datos descargados exitosamente. Generando archivos...")
        
        # 2. Generar los 3 tipos de archivos
        generate_m3u(data)
        generate_xmltv(data)
        generate_json_output(data)
        
        print("\n¡Proceso completado!")
    else:
        print("No se pudieron obtener datos. Saliendo del script.")


if __name__ == "__main__":
    main()
