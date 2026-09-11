import sys
import os
from os import path
import time
import requests
import subprocess
import configparser
import re
import json
import html
from lxml import etree, html
from datetime import datetime
from dateutil import parser, tz
import xml.etree.ElementTree as ET
from PyQt5.QtGui import QIcon, QFont, QImage, QPixmap, QColor
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, QObject, pyqtSignal, 
    QRunnable, pyqtSlot, QThreadPool, QModelIndex, QAbstractItemModel, QVariant
)
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QLineEdit, QLabel, QPushButton,
    QListWidget, QWidget, QFileDialog, QCheckBox, QSizePolicy, QHBoxLayout,
    QDialog, QFormLayout, QDialogButtonBox, QTabWidget, QListWidgetItem,
    QSpinBox, QMenu, QAction, QTextEdit, QGridLayout, QMessageBox, QListView,
    QTreeWidget, QTreeWidgetItem, QTreeView
)

import base64

CONNECTION_HEADER           = "Keep-Alive"
CONTENT_HEADER              = "gzip, deflate"
DEFAULT_USER_AGENT_HEADER   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"

# Default network values. Keep immutable defaults separate from the active values
# so the Advanced network settings dialog can reliably restore factory settings.
DEFAULT_CONNECTION_TIMEOUT  = 3
DEFAULT_READ_TIMEOUT         = 30
DEFAULT_LIVE_STATUS_TIMEOUT  = 7
DEFAULT_LIVE_STATUS_RETRIES  = 2
DEFAULT_ACCOUNT_INFO_REFRESH_INTERVAL = 60

# LIVE status retries are additional attempts, so the default value of 2 allows
# up to 3 probes including the initial request.
CONNECTION_TIMEOUT       = DEFAULT_CONNECTION_TIMEOUT
READ_TIMEOUT             = DEFAULT_READ_TIMEOUT
LIVE_STATUS_TIMEOUT      = DEFAULT_LIVE_STATUS_TIMEOUT
LIVE_STATUS_RETRIES      = DEFAULT_LIVE_STATUS_RETRIES
LIVE_STATUS_RETRY_DELAY  = 0.5
LIVE_STATUS_CHUNK_SIZE   = 4096
MAX_LIVE_STATUS_RETRIES  = 10


class AccountInfoWorkerSignals(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)


class AccountInfoWorker(QRunnable):
    """Fetch only account/server metadata from the Xtream player API."""

    def __init__(self, server, username, password, user_agent):
        super().__init__()
        self.server = server
        self.username = username
        self.password = password
        self.user_agent = user_agent
        self.signals = AccountInfoWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            headers = {
                "Connection": CONNECTION_HEADER,
                "Accept-Encoding": CONTENT_HEADER,
                "User-Agent": self.user_agent or DEFAULT_USER_AGENT_HEADER
            }
            response = requests.get(
                f"{self.server}/player_api.php",
                params={
                    'username': self.username,
                    'password': self.password,
                    'action': ''
                },
                headers=headers,
                timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT)
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("The provider returned invalid account information")
            self.signals.finished.emit(data)
        except Exception as error:
            self.signals.error.emit(str(error))

class FetchDataWorkerSignals(QObject):
    finished        = pyqtSignal(dict, dict, dict)
    error           = pyqtSignal(str)
    progress_bar    = pyqtSignal(int, int, str)
    show_error_msg  = pyqtSignal(str, str)
    show_info_msg   = pyqtSignal(str, str)

class FetchDataWorker(QRunnable):
    def __init__(self, server, username, password, live_url_format, movie_url_format,
                 series_url_format, parent=None, enabled_stream_types=None):
        super().__init__()
        self.server            = server
        self.username          = username
        self.password          = password
        self.live_url_format   = live_url_format
        self.movie_url_format  = movie_url_format
        self.series_url_format = series_url_format
        # Copy the selection because the Settings checkboxes may change while this
        # worker is running. A missing value keeps the historical all-content default.
        enabled_stream_types = enabled_stream_types or {
            'LIVE': True,
            'Movies': True,
            'Series': True
        }
        self.enabled_stream_types = {
            stream_type: bool(enabled_stream_types.get(stream_type, True))
            for stream_type in ('LIVE', 'Movies', 'Series')
        }
        self.parent            = parent
        self.signals           = FetchDataWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            categories_per_stream_type = {
                'LIVE': [],
                'Movies': [],
                'Series': []
            }
            entries_per_stream_type = {
                'LIVE': [],
                'Movies': [],
                'Series': []
            }

            #Create header
            # Fall back to the default UA when the user hasn't picked one — sending an
            # empty User-Agent makes some providers return 403 or empty category lists
            # (related to issues #69 and #10).
            ua = (self.parent.current_user_agent or "").strip() or DEFAULT_USER_AGENT_HEADER
            headers = {
                "Connection": CONNECTION_HEADER,
                "Accept-Encoding": CONTENT_HEADER,
                "User-Agent": ua
            }

            params = {
                'username': self.username,
                'password': self.password,
                'action': ''
            }

            host_url = f"{self.server}/player_api.php"

            print("Going to fetch IPTV data")

            #Get IPTV info
            self.signals.progress_bar.emit(0, 5, "Fetching IPTV info")
            try:
                iptv_info_resp = requests.get(host_url, params=params, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))
                iptv_info_resp.raise_for_status()

                iptv_info_data = iptv_info_resp.json()
            except Exception as e:
                iptv_info_data = {}

                print(f"failed fetching IPTV data: {e}")

            #Load cached data
            cached_data = {}

            #Check if cache file exists
            if path.isfile(self.parent.cache_file):
                print("Cache file is there")

                try:
                    print("Loading cached data")
                    with open(self.parent.cache_file, 'r') as cache_file:
                        cached_data = json.load(cache_file)
                except Exception as e:
                    cached_data = {}

                    # self.signals.show_error_msg.emit('Failed loading cache file', 
                    #         "Failed loading cache file.\n"
                    #         "Please check if it is empty or corrupted.")
                    print("Failed loading cache file. Please check if it is empty or corrupted.")

            config = configparser.ConfigParser()
            try:
                config.read(self.parent.user_data_file)
            except (configparser.Error, UnicodeDecodeError):
                config = configparser.ConfigParser()

            if config.has_option('Debug', 'load_with_cache') and config['Debug']['load_with_cache'] == 'True':   #For testing purposes only
                for stream_type in ('LIVE', 'Movies', 'Series'):
                    if not self.enabled_stream_types[stream_type]:
                        continue
                    categories_per_stream_type[stream_type] = cached_data.get(
                        f'{stream_type} categories', []
                    )
                    entries_per_stream_type[stream_type] = cached_data.get(stream_type, [])
            else:
                # Describe the six provider collections in one table so each content
                # toggle controls both its category and stream requests consistently.
                request_plan = (
                    ('LIVE', 'categories', 'get_live_categories', 'LIVE categories', 5, 10),
                    ('Movies', 'categories', 'get_vod_categories', 'Movies categories', 10, 20),
                    ('Series', 'categories', 'get_series_categories', 'Series categories', 20, 30),
                    ('LIVE', 'streams', 'get_live_streams', 'LIVE', 30, 40),
                    ('Movies', 'streams', 'get_vod_streams', 'Movies', 40, 60),
                    ('Series', 'streams', 'get_series', 'Series', 60, 80),
                )

                for stream_type, collection, action, cache_key, start, end in request_plan:
                    if not self.enabled_stream_types[stream_type]:
                        print(f"Skipping disabled {stream_type} {collection}")
                        continue

                    label = f"{stream_type} {collection}"
                    print(f"Fetching {label}")
                    self.signals.progress_bar.emit(start, end, f"Fetching {label}")
                    try:
                        params['action'] = action
                        response = requests.get(
                            host_url,
                            params=params,
                            headers=headers,
                            timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT)
                        )
                        response.raise_for_status()
                        result = response.json()
                    except Exception as e:
                        print(f"Failed fetching {label}: {e}")
                        result = cached_data.get(cache_key, [])
                        if result:
                            print(f"Loaded {label} from cache")

                    destination = (
                        categories_per_stream_type
                        if collection == 'categories'
                        else entries_per_stream_type
                    )
                    destination[stream_type] = result

                print("going to create cached data")

                # Preserve cached collections for disabled content. Disabling Movies,
                # for example, must not erase its useful fallback data from disk.
                cache_to_write = dict(cached_data)
                for stream_type in ('LIVE', 'Movies', 'Series'):
                    if self.enabled_stream_types[stream_type]:
                        cache_to_write[f'{stream_type} categories'] = (
                            categories_per_stream_type[stream_type]
                        )
                        cache_to_write[stream_type] = entries_per_stream_type[stream_type]

                all_cached_data = json.dumps(cache_to_write, indent=4)

                with open(self.parent.cache_file, 'w') as cache_file:
                    cache_file.write(all_cached_data)

            # self.set_progress_bar(100, "Finished loading data")
            self.signals.progress_bar.emit(80, 100, "Finished Fetching data")

            fav_data = {}

            #Check if cache file exists
            if path.isfile(self.parent.favorites_file):
                print("Favorites file is there")

                with open(self.parent.favorites_file, 'r') as fav_file:
                    fav_data = json.load(fav_file)

            print("Preparing streaming data")
            #Make streaming URL in each entry except for the series
            for tab_name in entries_per_stream_type.keys():
                for idx, entry in enumerate(entries_per_stream_type[tab_name]):
                    #Get stream type. If no stream_type is found it is series
                    stream_type         = entry.get('stream_type', 'series')
                    stream_id           = entry.get("stream_id", -1)
                    series_id           = entry.get("series_id", -1)
                    container_extension = entry.get("container_extension", "m3u8")

                    #Correct for any vague other stream types. Series stream type is already fixed by code above.
                    if "live" in stream_type:
                        stream_type = "live"

                    if "movie" in stream_type:
                        stream_type = "movie"

                    #Check if stream_id is valid
                    if stream_id:
                        entries_per_stream_type[tab_name][idx]["url"] = self.generate_url(stream_type, stream_id, container_extension)

                        #Check if stream id is in favorites list in userdata.ini
                        if stream_id in fav_data.get('stream_ids', []):
                            #Add "favorite" parameter to entries_per_stream_type and set to True or False depending if inside userdata.ini
                            entries_per_stream_type[tab_name][idx]['favorite'] = True
                        else:
                            entries_per_stream_type[tab_name][idx]['favorite'] = False
                    else:
                        entries_per_stream_type[tab_name][idx]["url"] = None

                    #Check if stream type is series
                    if stream_type == 'series':
                        #Create stream type key for series data
                        entries_per_stream_type[tab_name][idx]["stream_type"] = stream_type

                        #Check if series_id is valid
                        if series_id:
                            #Check if series id is in favorites list in userdata.ini
                            if series_id in fav_data.get('series_ids', []):
                                #Add "favorite" parameter to entries_per_stream_type and set to True or False depending if inside userdata.ini
                                entries_per_stream_type[tab_name][idx]['favorite'] = True
                            else:
                                entries_per_stream_type[tab_name][idx]['favorite'] = False

            #Send received data to processing function
            self.signals.finished.emit(iptv_info_data, categories_per_stream_type, entries_per_stream_type)

            print("Finished downloading IPTV data")

        except Exception as e:
            print(f"Exception! {e}")
            self.signals.error.emit(str(e))

    def generate_url(self, stream_type, stream_id, container_extension):
        # Select the appropriate format string
        if stream_type == 'live':
            fmt = self.live_url_format
        elif stream_type == 'movie':
            fmt = self.movie_url_format
        else:
            # Fallback format if unknown type
            fmt = "{server}/{stream_type}/{username}/{password}/{stream_id}.{container_extension}"
    
        # Remove extension if not included in the format string
        if ".{container_extension}" not in fmt:
            container_extension = ""
    
        # Format and return the URL
        return fmt.format(
            server=self.server,
            username=self.username,
            password=self.password,
            stream_type=stream_type,
            stream_id=stream_id,
            container_extension=container_extension
        )

class MovieInfoFetcherSignals(QObject):
    finished    = pyqtSignal(dict, dict)
    error       = pyqtSignal(str)

class MovieInfoFetcher(QRunnable):
    def __init__(self, server, username, password, vod_id, parent=None):
        super().__init__()
        self.server     = server
        self.username   = username
        self.password   = password
        self.vod_id     = vod_id
        self.parent     = parent
        self.signals    = MovieInfoFetcherSignals()

    @pyqtSlot()
    def run(self):
        try:
            #Set request parameters
            # headers = {'User-Agent': CUSTOM_USER_AGENT}
            #Create header
            # Fall back to the default UA when the user hasn't picked one — sending an
            # empty User-Agent makes some providers return 403 or empty category lists
            # (related to issues #69 and #10).
            ua = (self.parent.current_user_agent or "").strip() or DEFAULT_USER_AGENT_HEADER
            headers = {
                "Connection": CONNECTION_HEADER,
                "Accept-Encoding": CONTENT_HEADER,
                "User-Agent": ua
            }
            host_url = f"{self.server}/player_api.php"
            params = {
                'username': self.username,
                'password': self.password,
                'action': 'get_vod_info',
                'vod_id': self.vod_id
            }

            #Request vod info
            vod_info_resp = requests.get(host_url, params=params, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))

            #Get vod info data
            vod_info_data = vod_info_resp.json()

            #Get info and movie data
            vod_info = vod_info_data.get('info', {})
            vod_data = vod_info_data.get('movie_data', {})

            #Check if the variable types are valid
            if not isinstance(vod_info, dict):
                vod_info = {}

            if not isinstance(vod_data, dict):
                vod_data = {}

            #Return movie info data
            self.signals.finished.emit(vod_info, vod_data)
        except Exception as e:
            print(f"Failed fetching movie info: {e}")
            self.signals.error.emit(str(e))

class SeriesInfoFetcherSignals(QObject):
    finished    = pyqtSignal(dict, bool)
    error       = pyqtSignal(str)

class SeriesInfoFetcher(QRunnable):
    def __init__(self, server, username, password, series_id, is_show_request, parent=None):
        super().__init__()
        self.server             = server
        self.username           = username
        self.password           = password
        self.series_id          = series_id
        self.is_show_request    = is_show_request
        self.parent             = parent
        self.signals            = SeriesInfoFetcherSignals()

    @pyqtSlot()
    def run(self):
        try:
            #Set request parameters
            # headers = {'User-Agent': CUSTOM_USER_AGENT}
            #Create header
            # Fall back to the default UA when the user hasn't picked one — sending an
            # empty User-Agent makes some providers return 403 or empty category lists
            # (related to issues #69 and #10).
            ua = (self.parent.current_user_agent or "").strip() or DEFAULT_USER_AGENT_HEADER
            headers = {
                "Connection": CONNECTION_HEADER,
                "Accept-Encoding": CONTENT_HEADER,
                "User-Agent": ua
            }
            host_url = f"{self.server}/player_api.php"
            params = {
                'username': self.username,
                'password': self.password,
                'action': 'get_series_info',
                'series_id': self.series_id
            }

            #Request series info
            series_info_resp = requests.get(host_url, params=params, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))

            #Get series info data
            series_info_data = series_info_resp.json()

            #Check if the variable type is valid
            if not isinstance(series_info_data, dict):
                series_info_data = {}

            #Return series info data
            self.signals.finished.emit(series_info_data, self.is_show_request)
        except Exception as e:
            print(f"Failed fetching series info: {e}")
            self.signals.error.emit(str(e))
        
class ImageFetcherSignals(QObject):
    finished    = pyqtSignal(QPixmap, str)
    error       = pyqtSignal(str)

class ImageFetcher(QRunnable):
    def __init__(self, img_url, stream_type, parent=None):
        super().__init__()
        self.img_url        = img_url
        self.stream_type    = stream_type
        self.parent         = parent
        self.signals        = ImageFetcherSignals()

    @pyqtSlot()
    def run(self):
        try:
            # Skip the network call entirely if the entry didn't have a logo/cover URL —
            # otherwise requests raises "No scheme supplied" and floods the log.
            if not self.img_url or not str(self.img_url).strip():
                image = QPixmap(self.parent.path_to_no_img)
                self.signals.finished.emit(image, self.stream_type)
                return

            # Fall back to the default UA when the user hasn't picked one — sending an
            # empty User-Agent makes some providers return 403 or empty category lists
            # (related to issues #69 and #10).
            ua = (self.parent.current_user_agent or "").strip() or DEFAULT_USER_AGENT_HEADER
            headers = {
                "Connection": CONNECTION_HEADER,
                "Accept-Encoding": CONTENT_HEADER,
                "User-Agent": ua
            }

            #Request image
            image_resp = requests.get(self.img_url, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))

            #Check if response code is valid, otherwise set replacement image
            resp_status = image_resp.status_code
            if resp_status == 404:
                #Set 404 error as image
                image = QPixmap(self.parent.path_to_404_img)

            elif not resp_status == 200:
                #Set no image
                image = QPixmap(self.parent.path_to_no_img)

            else:
                #Create QPixmap from image data
                image = QPixmap()
                image.loadFromData(image_resp.content)  #Don't combine this with the previous line, then it doesn't work

            #Check if Pixmap is valid
            if image.isNull():
                image = QPixmap(self.parent.path_to_no_img)

            #Emit image
            self.signals.finished.emit(image, self.stream_type)
        except Exception as e:
            print(f"Failed fetching image: {e}")

            #Emit no image placeholder
            image = QPixmap(self.parent.path_to_no_img)
            self.signals.finished.emit(image, self.stream_type)
            self.signals.error.emit(str(e))

class SearchWorkerSignals(QObject):
    list_widget = pyqtSignal(list, str)
    error = pyqtSignal(str)

class SearchWorker(QRunnable):
    def __init__(self, stream_type, currently_loaded_entries, list_widgets, text):
        super().__init__()
        self.stream_type = stream_type
        self.currently_loaded_entries = currently_loaded_entries[0]
        self.list_widgets = list_widgets[0]
        self.text = text

        self.signals = SearchWorkerSignals()

        # self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        try:
            self.list_widgets[self.stream_type].clear()
            print("starting searching through entries")

            for entry in self.currently_loaded_entries[self.stream_type]:
                if self.text.lower() in entry['name'].lower():
                    item = QListWidgetItem(entry['name'])
                    item.setData(Qt.UserRole, entry)

                    self.list_widgets[self.stream_type].addItem(item)

                    print(entry['name'])

            self.signals.list_widget.emit([self.list_widgets[self.stream_type]], self.stream_type)
        except Exception as e:
            print(f"failed search worker: {e}")

class EPGWorkerSignals(QObject):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

class EPGWorker(QRunnable):
    def __init__(self, server, username, password, stream_id, parent=None):
        super().__init__()
        self.server     = server
        self.username   = username
        self.password   = password
        self.stream_id  = stream_id
        self.parent     = parent
        self.signals    = EPGWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            #Creating url for requesting EPG data for specific stream
            epg_url = f"{self.server}/player_api.php?username={self.username}&password={self.password}&action=get_simple_data_table&stream_id={self.stream_id}"
            # headers = {'User-Agent': CUSTOM_USER_AGENT}
            #Create header
            # Fall back to the default UA when the user hasn't picked one — sending an
            # empty User-Agent makes some providers return 403 or empty category lists
            # (related to issues #69 and #10).
            ua = (self.parent.current_user_agent or "").strip() or DEFAULT_USER_AGENT_HEADER
            headers = {
                "Connection": CONNECTION_HEADER,
                "Accept-Encoding": CONTENT_HEADER,
                "User-Agent": ua
            }

            #Requesting EPG data
            response = requests.get(epg_url, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))
            epg_data = response.json()

            #Decrypt EPG data with base 64
            decrypted_epg_data = self.decryptEPGData(epg_data)

            self.signals.finished.emit(decrypted_epg_data)
        except Exception as e:
            self.signals.error.emit(str(e))

    def _decode_epg_text(self, raw_bytes):
        # EPG payloads come back base64-encoded. Most providers wrap UTF-8 text,
        # but MENA-region providers (e.g. anghami.us) wrap Windows-1256 (Arabic ANSI).
        # Decoding cp1256 bytes as UTF-8 either raises or yields mojibake, so try
        # the common encodings in order and fall back to a replace decode last.
        for enc in ("utf-8", "utf-8-sig", "cp1256", "iso-8859-6", "cp1252"):
            try:
                return raw_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw_bytes.decode("utf-8", errors="replace")

    def decryptEPGData(self, epg_data):
        try:
            decrypted_epg_data = []

            for epg_entry in epg_data['epg_listings']:
                #Get start, stop time and date
                start_timestamp = datetime.fromtimestamp(int(epg_entry['start_timestamp']))
                stop_timestamp  = datetime.fromtimestamp(int(epg_entry['stop_timestamp']))
                date            = f"{start_timestamp.day:02}-{start_timestamp.month:02}-{start_timestamp.year}"

                #Decode program name and description — see _decode_epg_text for the encoding fallback.
                program_name        = self._decode_epg_text(base64.b64decode(epg_entry['title']))
                program_description = self._decode_epg_text(base64.b64decode(epg_entry['description']))

                #Put only necessary EPG data in list
                decrypted_epg_data.append({
                    'start_time': start_timestamp,
                    'stop_time': stop_timestamp,
                    'program_name': program_name,
                    'description': program_description,
                    'date': date
                    })

            #return decrypted EPG data
            return decrypted_epg_data
        except Exception as e:
            print(f"failed decrypting: {e}")

class OnlineWorkerSignals(QObject):
    finished = pyqtSignal(int, str)
    error = pyqtSignal(str)

class OnlineWorker(QRunnable):
    def __init__(self, stream_id, url, parent=None):
        super().__init__()
        self.stream_id  = int(stream_id)
        self.url        = url
        self.parent     = parent
        self.signals    = OnlineWorkerSignals()

    @pyqtSlot()
    def run(self):
        """Probe a LIVE stream and emit one final status after all retries."""

        # Fall back to the default UA when the user has not picked one. Sending an
        # empty User-Agent makes some providers return 403 or empty responses.
        ua = (self.parent.current_user_agent or "").strip() or DEFAULT_USER_AGENT_HEADER
        headers = {
            "Connection": CONNECTION_HEADER,
            "Accept-Encoding": CONTENT_HEADER,
            "User-Agent": ua
        }

        # Clamp the global value because userdata.ini can be edited manually and
        # therefore cannot be trusted to respect the GUI validator.
        retry_count = max(0, min(int(LIVE_STATUS_RETRIES), MAX_LIVE_STATUS_RETRIES))
        best_status = False
        received_response = False
        last_error = None

        # Do not emit a red state between attempts. A transient provider failure
        # should not make the traffic light flicker before a later probe succeeds.
        for attempt in range(retry_count + 1):
            try:
                stream_status = self.requestStatus(headers)
                received_response = True

                # A confirmed successful probe is definitive and needs no retry.
                if stream_status is True:
                    self.signals.finished.emit(self.stream_id, str(stream_status))
                    return

                # Preserve "Maybe" over False when the provider reports a stream
                # that appears to be starting, even if a later retry fails.
                if stream_status == "Maybe":
                    best_status = "Maybe"
            except Exception as e:
                last_error = e

            if attempt < retry_count:
                time.sleep(LIVE_STATUS_RETRY_DELAY)

        # HTTP responses produce a final red/amber status. The unknown state is
        # reserved for the case where every attempt failed at the network layer.
        if received_response:
            self.signals.finished.emit(self.stream_id, str(best_status))
        else:
            self.signals.error.emit(str(last_error))

    def requestStatus(self, headers):
        """Read one small chunk instead of waiting for a continuous stream to end."""

        # Direct .ts streams may never finish. Streaming the response and closing it
        # after the first 4 KiB proves that bytes are arriving without downloading
        # the programme itself or holding an extra provider connection open.
        with requests.get(
            self.url,
            headers=headers,
            timeout=(CONNECTION_TIMEOUT, LIVE_STATUS_TIMEOUT),
            stream=True
        ) as response:
            response_code = response.status_code
            url_data = response.url
            received_data = False

            if response_code == 200:
                for chunk in response.iter_content(chunk_size=LIVE_STATUS_CHUNK_SIZE):
                    if chunk:
                        received_data = True
                        url_data += "\n" + chunk.decode("utf-8", errors="ignore")
                        break

                # A successful HTTP response without payload does not prove that the
                # channel is usable, so treat it as an offline probe.
                if not received_data:
                    return False

        return self.checkStatus(response_code, url_data)

    def checkStatus(self, response_code, url_data):
        if response_code != 200:  # need HTTP OK status
            return False

        # Provider-generated playlists are not consistent about letter case.
        normalized_url_data = url_data.lower()

        if "offline" in normalized_url_data: #some providers use offline.m3u8 as a dummy video file
            return False
        
        if "ext-x-endlist" in normalized_url_data: #m3u file is saying stream is over
            return False
        
        if "#ext-x-media-sequence:0" in normalized_url_data:                 #some providers respond with a fresh "Stream starting soon" stream
            if "_0.ts" in normalized_url_data and "_1.ts" not in normalized_url_data:   #this technically just means a stream is freshly started, hence the "Maybe" online
                return "Maybe"                                    #officially, see https://datatracker.ietf.org/doc/html/rfc8216#section-4.3.3.2

        return True
