import requests
import json
import datetime
from tqdm import tqdm
from pprint import pprint
import os.path
from urllib.request import urlopen
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseUpload
from urllib3.packages.six import BytesIO


class VK:
    base_url = 'https://api.vk.com/method/'

    def __init__(self, token, api_ver):
        self.params = {
            'access_token': token,
            'v': api_ver
        }

    def screen_name_to_user_id(self, screen_name):
        params_user = {
            'screen_name': screen_name
        }
        user_id = requests.get(f'{self.base_url}utils.resolveScreenName', params={**self.params, **params_user}).json()[
            'response']['object_id']
        return user_id

    def find_photos_in_vk(self, user_id, photo_count=5, album_id='profile'):
        """
        photo_count: количество фотографий для сохранения на сетевой диск
        album_id:
        wall — фотографии со стены
        profile — фотографии профиля
        saved — сохраненные фотографии
        """
        # ===(если вместо числового id пользователь ввел свое 'screen_name', преобразуем его в id)==
        if not user_id.isdigit():
            user_id = int(self.screen_name_to_user_id(user_id))

        params_photo = {
            'owner_id': int(user_id),
            'album_id': album_id,
            'extended': '1'
        }

        # ===(получаем информацию о всех фотографиях в альбоме)==
        response_photo_info = requests.get(f'{self.base_url}photos.get', params={**self.params, **params_photo}).json()
        if 'error' in response_photo_info.keys():
            return f'vk api error {response_photo_info["error"]["error_code"]}: {response_photo_info["error"]["error_msg"]}'
        else:
            # ===(если количество фотографий в альбоме меньше, чем то что необходимо сохранить, будем сохранять все имеющиеся в альбоме.)==
            if int(len(response_photo_info['response']['items'])) < int(photo_count):
                photo_count = len(response_photo_info['response']['items'])

            # ===(сортировка списка размеров фотографии от большей к меньшей)==
            for count in range(len(response_photo_info['response']['items'])):
                response_photo_info['response']['items'][count]['sizes'] = sorted(
                    response_photo_info['response']['items'][count]['sizes'], key=lambda x: x['height'] * x['width'],
                    reverse=True)

            # ===(сортировка фотографий в альбоме по размеру от большей к меньшей)==
            response_photo_info['response']['items'] = sorted(response_photo_info['response']['items'],
                                                              key=lambda x: x['sizes'][0]['height'] * x['sizes'][0][
                                                                  'width'], reverse=True)

            # ===(создаем список словарей и наполняем его данными, заданного количества, самых больших фотографий. в качестве имени используем количество лайков, если количество лайков одинаково, то добавляем дату загрузки.)==
            all_photo = []
            photo_likes_list = []
            for count in range(photo_count):
                vk_photo = {}
                # ===(выделяем из url расширение фотографии)==
                vk_path_to_url = response_photo_info['response']['items'][count]['sizes'][0]['url']
                if '?' in vk_path_to_url:
                    vk_photo_extension = str(
                        vk_path_to_url[:int(vk_path_to_url.find('?'))][int(vk_path_to_url.rfind('.')):])
                else:
                    vk_photo_extension = str(vk_path_to_url[int(vk_path_to_url.rfind('.')):])
                if response_photo_info['response']['items'][count]['likes']['count'] in photo_likes_list:
                    vk_photo['file_name'] = str(
                        response_photo_info['response']['items'][count]['likes']['count']) + str(
                        datetime.datetime.utcfromtimestamp(
                            response_photo_info['response']['items'][count]['date']).strftime(
                            '_%Y-%m-%d_%H-%M-%S')) + vk_photo_extension
                else:
                    vk_photo['file_name'] = str(
                        response_photo_info['response']['items'][count]['likes']['count']) + vk_photo_extension
                vk_photo['size'] = response_photo_info['response']['items'][count]['sizes'][0]['type']
                vk_photo['url'] = response_photo_info['response']['items'][count]['sizes'][0]['url']
                photo_likes_list.append(response_photo_info['response']['items'][count]['likes']['count'])
                all_photo.append(vk_photo)
            return all_photo


class Yandex:
    base_url = 'https://cloud-api.yandex.net:443/'

    def __init__(self, token):
        self.token = token

    def upload_file_on_disk(self, social_web_photos, folder_name):
        if type(social_web_photos) is str:  # строковый тип переменная принимает в случае ошибки при выборке фотографий и содержит в себе ее описание
            print('\n' + social_web_photos)
        else:
            folder_name = f'{folder_name}/'
            ya_headers = {
                'accept': 'application/json',
                'authorization': f'OAuth {self.token}'
            }

            requests.put(self.base_url + 'v1/disk/resources', headers=ya_headers, params={'path': folder_name}).json()
            print(f'\nЗагрузка файлов на Yandex Disc:')
            img_data = []
            for img in tqdm(social_web_photos):
                requests.post(self.base_url + 'v1/disk/resources/upload', headers=ya_headers,
                              params={'path': f'{folder_name}{img["file_name"]}', 'url': img['url'],
                                      'overwrite': 'true'})
                img_data_temp = {
                    'file_name': img['file_name'],
                    'size': img['size']
                }
                img_data.append(img_data_temp)
                with open('img_data.json', 'w') as file:
                    json.dump(img_data, file, ensure_ascii=False, indent=2)
            print(f'Процедура копирования завершена.')
            if os.path.exists('img_data.json'):
                print(f'Информация о загруженных файлах находится в: "img_data.json"')


class Google:
    def __init__(self, api_ver):
        self.api_ver = api_ver

    def authorization(self):
        SCOPES = ['https://www.googleapis.com/auth/drive']
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        drive_service = build('drive', self.api_ver, credentials=creds)
        return drive_service

    def create_folder(self, folder_name, drive_service):
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        file = drive_service.files().create(body=file_metadata, fields='id').execute()
        folder_id = file.get('id')
        return folder_id

    def upload_file(self, social_web_photos, folder_name):
        drive_service = self.authorization()
        folder_id = self.create_folder(folder_name, drive_service)
        if type(social_web_photos) is str:  # строковый тип переменная принимает в случае ошибки при выборке фотографий и содержит в себе ее описание
            print('\n' + social_web_photos)
        else:
            img_data = []
            print(f'\nЗагрузка файлов в Google Drive:')
            for img in tqdm(social_web_photos):
                file_url = img['url']
                response = urlopen(file_url)
                bytes_file = BytesIO(response.read())
                media_body = MediaIoBaseUpload(bytes_file, mimetype='image/jpeg', resumable=True)
                body = {
                    'name': img['file_name'],
                    'parents': [folder_id]
                }
                drive_service.files().create(body=body, media_body=media_body).execute()
                img_data_temp = {
                    'file_name': img['file_name'],
                    'size': img['size']
                }
                img_data.append(img_data_temp)
                with open('img_data.json', 'w') as file:
                    json.dump(img_data, file, ensure_ascii=False, indent=2)
            print(f'Процедура копирования завершена.')
            if os.path.exists('img_data.json'):
                print(f'Информация о загруженных файлах находится в: "img_data.json"')


def input_search_parameters():
    social_web_photos = None
    folder_name = 'vk_photos'
    social_web = 'vk'
    photo_count = 5  # количество фотографий для сохранения на сетевой диск

    photo_count = input('Сколько фотографий скопировать? ')
    if photo_count.isdigit() and int(photo_count) > 0:
        photo_count = int(photo_count)
    else:
        print('Введено некорректное значение количества фотографий.')
        return

    if social_web == 'vk':
        vk_user_id = input('Введите id пользователя VKontakte: ')
        vk_token = input('Введите token для VK api: ')
        vk_api_ver = '5.80'
        vk_album_id = 'profile'  # wall — фотографии со стены, profile — фотографии профиля, saved — сохраненные фотографии
        vk_album_id = input('''Из какого альбома сохранить фотографии?
W => wall — фотографии со стены
P => profile — фотографии профиля
S => saved — сохраненные фотографии
Что выберете? ''').lower()
        if vk_album_id in ['w', 'wall']:
            vk_album_id = 'wall'
        elif vk_album_id in ['p', 'profile']:
            vk_album_id = 'profile'
        elif vk_album_id in ['s', 'saved']:
            vk_album_id = 'saved'
        else:
            vk_album_id = 'wall'  # по-умолчанию
        vk_user = VK(vk_token, vk_api_ver)
        social_web_photos = vk_user.find_photos_in_vk(vk_user_id, photo_count, vk_album_id)
    else:
        print('Выбрана недопустимая социальная сеть.')
        return

    web_disk = input('В какой облачный сервис скопировать фотографии (Yandex/Google)? ').lower()
    if web_disk in ['yandex disk', 'yandex', 'y']:
        yandex_token = input('Введите токен с Полигона Яндекс.Диск: ')
        yandex_disk = Yandex(yandex_token)
        yandex_disk.upload_file_on_disk(social_web_photos, folder_name)
    elif web_disk in ['google drive', 'google', 'g', 'gg']:
        google_api_ver = 'v3'
        google_drive = Google(google_api_ver)
        google_drive.upload_file(social_web_photos, folder_name)
    else:
        print('Выбран недопустимый облачный сервис.')


input_search_parameters()
