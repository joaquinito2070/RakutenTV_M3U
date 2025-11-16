# system imports
import os
# import pprint
from collections import namedtuple
from typing import List

# 3rd parties imports
import requests
from dotenv import load_dotenv


# Channel definition
CHANNEL_FIELDS = [
    "id",
    "numerical_id",
    "title",
    "type",
    "channel_number",
    "category",
    "language_ids",
]

Channel = namedtuple("Channel", CHANNEL_FIELDS)

# Load configuration
load_dotenv()


class Api:
    api_scheme = "https"
    api_domain = "gizmo.rakuten.tv"
    api_base_path = "/v3"
    api_base_url = "{}://{}{}".format(
        api_scheme,
        api_domain,
        api_base_path
    )

    origin = "https://rakuten.tv"
    referer = "https://rakuten.tv/"
    user_agent = "Mozilla/5.0 (X11; Linux x86_64; rv:98.0) Gecko/20100101 Firefox/98.0"

    language = os.getenv('CLASSIFICATION', 'it') # El script run_generator.py lo cambiará

    classification_id = {
        "al": 270, "at": 300, "ba": 245, "be": 308, "bg": 269, "ch": 319,
        "cz": 272, "de": 307, "dk": 283, "ee": 288, "es": 5, "fi": 284,
        "fr": 23, "gr": 279, "hr": 302, "ie": 41, "is": 287, "it": 36,
        "jp": 309, "lt": 290, "lu": 74, "me": 259, "mk": 275, "nl": 69,
        "no": 286, "pl": 277, "pt": 64, "ro": 268, "rs": 266, "se": 282,
        "sk": 273, "uk": 18,
    }


    @classmethod
    def get_live_channels(cls):
        path = "/live_channels"
        headers = {
            "Origin": cls.origin,
            "Referer": cls.referer,
            "User_Agent": cls.user_agent,
        }
        query = {
            "classification_id": cls.classification_id[cls.language],
            "device_identifier": "web",
            "locale": cls.language,
            "market_code": cls.language,
            "page": 1,
            "per_page": 100,
        }
        
        try:
            response = requests.get(
                cls.api_base_url + path,
                headers=headers,
                params=query,
                timeout=10 # Añadido timeout
            )
            response.raise_for_status() # Lanza error si la respuesta es 4xx o 5xx
            return response.json()
        except (requests.exceptions.RequestException, requests.exceptions.JSONDecodeError) as e:
            print(f"  [Api Error get_live_channels] {e}")
            return {} # Devuelve dict vacío en error para evitar 'NoneType'

    @classmethod
    def get_live_channel_categories(cls):
        path = "/live_channel_categories"
        headers = {
            "Origin": cls.origin,
            "Referer": cls.referer,
            "User_Agent": cls.user_agent,
        }
        query = {
            "classification_id": cls.classification_id[cls.language],
            "device_identifier": "web",
            "locale": cls.language,
            "market_code": cls.language
        }

        try:
            response = requests.get(
                cls.api_base_url + path,
                headers=headers,
                params=query,
                timeout=10 # Añadido timeout
            )
            response.raise_for_status()
            return response.json()
        except (requests.exceptions.RequestException, requests.exceptions.JSONDecodeError) as e:
            print(f"  [Api Error get_live_channel_categories] {e}")
            return {} # Devuelve dict vacío en error

    @classmethod
    def get_live_streaming(cls, channel: Channel, session: requests.Session = None):
        path = "/avod/streamings"
        headers = {
            "Origin": cls.origin,
            "Referer": cls.referer,
            "User_Agent": cls.user_agent,
        }
        query = {
            "classification_id": cls.classification_id[cls.language],
            "device_identifier": "web",
            "device_stream_audio_quality": "2.0",
            "device_stream_hdr_type": "NONE",
            "device_stream_video_quality": "FHD",
            "disable_dash_legacy_packages": False,
            "locale": cls.language,
            "market_code": cls.language
        }

        data = {
            "audio_language": channel.language_ids[0] if channel.language_ids else "MIS",
            "audio_quality": "2.0",
            "classification_id": cls.classification_id[cls.language],
            "content_id": channel.id,
            "content_type": "live_channels",
            "device_serial": "not implemented",
            "player": "web:HLS-NONE:NONE",
            "strict_video_quality": False,
            "subtitle_language": "MIS",
            "video_type": "stream"
        }

        if session:
            caller = session
        else:
            caller = requests

        try:
            response = caller.post(
                cls.api_base_url + path,
                headers=headers,
                params=query,
                json=data,
                timeout=10 # Añadido timeout
            )
            response.raise_for_status()
            return response.json()
        except (requests.exceptions.RequestException, requests.exceptions.JSONDecodeError) as e:
            # No imprimimos error aquí porque es normal que falle si un canal no tiene stream
            return {} # Devuelve dict vacío en error

# methods
def map_channels_categories(api_response):
    # api_response ahora será {} si falló, .get() lo manejará bien
    categories = api_response.get("data", [])

    channels_categories_map = {}
    for category in categories:
        name = category.get("name", "no_category")
        channels = category.get("live_channels", [])

        for channel in channels:
            channels_categories_map[channel] = name

    return channels_categories_map


def map_channels_streams(channels: List[Channel]):
    session = requests.Session()
    ch_stream_map = {}

    for channel in channels:
        # stream_data será {} si la API falla, gracias a nuestra corrección
        stream_data = Api.get_live_streaming(channel, session)
        
        # --- Lógica de seguridad MEJORADA ---
        stream_url = "# no_url"
        # Obtenemos 'data' (default {}), luego 'stream_infos' (default None)
        stream_infos = stream_data.get("data", {}).get("stream_infos") 

        # Verificamos si 'stream_infos' es una lista y no está vacía
        if isinstance(stream_infos, list) and len(stream_infos) > 0:
            first_stream = stream_infos[0]
            # Verificamos si el primer elemento es un diccionario
            if isinstance(first_stream, dict):
                stream_url = first_stream.get("url", "# no_url")
        # --- Fin de la lógica de seguridad ---

        if stream_url != "# no_url":
            head, sep, tail = stream_url.partition('.m3u8')
            stream_url = head + sep

        ch_stream_map[channel.id] = stream_url

    return ch_stream_map


def get_channels() -> List[Channel]:
    live_channels_raw = Api.get_live_channels()
    categories_raw = Api.get_live_channel_categories()

    # live_channels_raw y categories_raw serán {} si fallan, no None
    # así que .get() funcionará sin problemas.

    # make channels/category lookup map
    cc_map = map_channels_categories(categories_raw)

    # list of all live channels
    # --- CORREGIDO: TIPO DE DATO ---
    ch_list: List[Channel] = [] # Antes decía 'List(Channels)'

    # .get("data", []) funcionará de forma segura
    channels = live_channels_raw.get("data", [])
    for channel in channels:

        ch_id = channel.get("id", "no_id")

        ch_languages = channel.get("labels", {}).get("languages", [])
        langs = []

        for lang in ch_languages:
            langs.append(lang.get("id"))

        ch = Channel(
            id = ch_id,
            numerical_id = int(channel.get("numerical_id", -1)),
            title = channel.get("title", "no_title"),
            type = channel.get("type", "no_type"),
            channel_number = int(channel.get("channel_number", -1)),
            category = cc_map.get(ch_id, "no_category"),
            language_ids = langs,
        )

        ch_list.append(ch)

    return ch_list
