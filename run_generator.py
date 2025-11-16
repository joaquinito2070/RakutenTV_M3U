import os
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List, Dict

# Importamos tu script original (ahora corregido)
import rakuten

# Tipos para claridad
Channel = rakuten.Channel
StreamsMap = Dict[str, str]

# Directorio para guardar los archivos generados
OUTPUT_DIR = "dist"


def generate_m3u(country_code: str, channels: List[Channel], streams: StreamsMap):
    """Genera un archivo .m3u para un país."""
    filename = os.path.join(OUTPUT_DIR, f"rakuten_{country_code}.m3u")
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        
        for channel in sorted(channels, key=lambda c: c.channel_number):
            stream_url = streams.get(channel.id)
            if not stream_url or stream_url == "# no_url":
                continue

            # Usamos el ID del canal para tvg-id
            tvg_id = channel.id
            # Usamos la categoría para group-title
            group_title = channel.category
            
            f.write(f'#EXTINF:-1 tvg-id="{tvg_id}" group-title="{group_title}",{channel.title}\n')
            f.write(f'{stream_url}\n')

    print(f"  -> Generado: {filename}")


def generate_json(country_code: str, channels: List[Channel], streams: StreamsMap):
    """Genera un archivo .json con información de canales y streams."""
    filename = os.path.join(OUTPUT_DIR, f"rakuten_{country_code}.json")
    
    data_list = []
    for channel in sorted(channels, key=lambda c: c.channel_number):
        stream_url = streams.get(channel.id)
        if not stream_url or stream_url == "# no_url":
            continue
            
        # Convertimos el namedtuple a dict para serializarlo fácil
        channel_data = channel._asdict()
        channel_data["stream_url"] = stream_url
        data_list.append(channel_data)
        
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data_list, f, indent=2, ensure_ascii=False)

    print(f"  -> Generado: {filename}")


def generate_xmltv(country_code: str, channels: List[Channel]):
    """Genera un archivo .xml (XMLTV) solo con información de canales."""
    filename = os.path.join(OUTPUT_DIR, f"rakuten_{country_code}.xml")
    
    # Raíz del documento XMLTV
    tv_root = ET.Element("tv")
    tv_root.set("generator-info-name", "RakutenGenerator")

    for channel in sorted(channels, key=lambda c: c.channel_number):
        ch_element = ET.SubElement(tv_root, "channel")
        ch_element.set("id", channel.id)
        
        display_name = ET.SubElement(ch_element, "display-name")
        display_name.text = channel.title
        
    # Convertir a string con formato "bonito" (pretty-print)
    xml_str = minidom.parseString(ET.tostring(tv_root)).toprettyxml(indent="  ", encoding="utf-8")
    
    with open(filename, "wb") as f:
        f.write(xml_str)
        
    print(f"  -> Generado: {filename}")


def combine_m3u_files(countries: List[str]):
    """Combina todos los .m3u en rakuten_all.m3u"""
    all_filename = os.path.join(OUTPUT_DIR, "rakuten_all.m3u")
    
    with open(all_filename, "w", encoding="utf-8") as outfile:
        outfile.write("#EXTM3U\n")
        
        for country in countries:
            country_filename = os.path.join(OUTPUT_DIR, f"rakuten_{country}.m3u")
            if not os.path.exists(country_filename):
                continue
                
            with open(country_filename, "r", encoding="utf-8") as infile:
                # Omitimos la cabecera #EXTM3U de cada archivo individual
                for line in infile:
                    if line.strip() != "#EXTM3U":
                        outfile.write(line)
                        
    print(f"\n[COMBINADO] Generado: {all_filename}")


def combine_json_files(countries: List[str]):
    """Combina todos los .json en rakuten_all.json"""
    all_filename = os.path.join(OUTPUT_DIR, "rakuten_all.json")
    all_data = []
    
    for country in countries:
        country_filename = os.path.join(OUTPUT_DIR, f"rakuten_{country}.json")
        if not os.path.exists(country_filename):
            continue
            
        with open(country_filename, "r", encoding="utf-8") as infile:
            try:
                country_data = json.load(infile)
                all_data.extend(country_data)
            except json.JSONDecodeError:
                print(f"  -> ERROR: No se pudo decodificar {country_filename}")

    # Eliminamos duplicados basados en 'id' de canal
    unique_data = {item['id']: item for item in all_data}.values()
    
    with open(all_filename, "w", encoding="utf-8") as outfile:
        json.dump(list(unique_data), outfile, indent=2, ensure_ascii=False)
        
    print(f"[COMBINADO] Generado: {all_filename} (canales únicos: {len(unique_data)})")


def combine_xmltv_files(countries: List[str]):
    """Combina todos los .xml en rakuten_all.xml"""
    all_filename = os.path.join(OUTPUT_DIR, "rakuten_all.xml")
    
    # Raíz del documento XMLTV combinado
    all_tv_root = ET.Element("tv")
    all_tv_root.set("generator-info-name", "RakutenGenerator")
    
    channel_ids = set()

    for country in countries:
        country_filename = os.path.join(OUTPUT_DIR, f"rakuten_{country}.xml")
        if not os.path.exists(country_filename):
            continue
            
        try:
            tree = ET.parse(country_filename)
            root = tree.getroot()
            for channel_element in root.findall("channel"):
                channel_id = channel_element.get("id")
                # Añadir solo si no lo hemos añadido ya
                if channel_id not in channel_ids:
                    all_tv_root.append(channel_element)
                    channel_ids.add(channel_id)
        except ET.ParseError:
            print(f"  -> ERROR: No se pudo parsear {country_filename}")

    # Convertir a string con formato "bonito"
    xml_str = minidom.parseString(ET.tostring(all_tv_root)).toprettyxml(indent="  ", encoding="utf-8")
    
    with open(all_filename, "wb") as f:
        f.write(xml_str)
        
    print(f"[COMBINADO] Generado: {all_filename} (canales únicos: {len(channel_ids)})")


def main():
    # Creamos el directorio de salida si no existe
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    countries_processed = []
    all_countries = list(rakuten.Api.classification_id.keys())
    
    for country in all_countries:
        print(f"\nProcesando país: {country.upper()}")
        
        # Modificamos la variable de clase en rakuten.py
        rakuten.Api.language = country
        
        try:
            channels = rakuten.get_channels()
            if not channels:
                print(f"  -> No se encontraron canales para {country}.")
                continue
                
            streams = rakuten.map_channels_streams(channels)
            
            # Generar los 3 tipos de archivos
            generate_m3u(country, channels, streams)
            generate_json(country, channels, streams)
            generate_xmltv(country, channels)
            
            countries_processed.append(country)
            
        except Exception as e:
            # Esta excepción ahora solo debería saltar por errores inesperados
            print(f"  -> ERROR procesando {country}: {e}")

    # --- Combinar archivos ---
    if countries_processed:
        combine_m3u_files(countries_processed)
        combine_json_files(countries_processed)
        combine_xmltv_files(countries_processed)
    
    print("\n¡Proceso completado!")


if __name__ == "__main__":
    main()
