import json

import pandas as pd
from geopy import Nominatim

NO_IMAGE= 'https://upload.wikimedia.org/wikipedia/commons/thumb/0/0a/No-image-available.png/480px-No-image-available.png'
def get_wikipedia_page(url):
    import requests

    print("Getting Wikipedia page..." ,url)

    try:
        response=requests.get(url,timeout=10)
        response.raise_for_status()

        return response.text

    except requests.RequestException as e:
        print(f"An error has occ:{e}")

def get_wikipedia_data(html):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, features='html.parser')
    table = soup.find_all("table")
    table_rows = table[2].find_all('tr')
    return table_rows

def clean_text(text):
    text = str(text).strip()
    text = text.replace('&nbsp', '')
    if text.find(' ♦'):
        text = text.split(' ♦')[0]
    if text.find('[') != -1:
        text = text.split('[')[0]
    if text.find(' (formerly)') != -1:
        text = text.split(' (formerly)')[0]

    return text.replace('\n', '')
def extract_wikipedia_data(**kwargs):
    url = kwargs['url']
    html = get_wikipedia_page(url)
    rows = get_wikipedia_data(html)
    data = []

    for i in range(1, len(rows)):
        tds = rows[i].find_all('td')
        values = {
            'rank': i,
            'stadium': clean_text(tds[0].text),
            'capacity': clean_text(tds[1].text).replace(',', '').replace('.', ''),
            'region': clean_text(tds[2].text),
            'country': clean_text(tds[3].text),
            'city': clean_text(tds[4].text),
            'images': 'https://' + tds[5].find('img').get('src').split("//")[1] if tds[5].find('img') else "NO_IMAGE",
            'home_team': clean_text(tds[6].text),
        }
        data.append(values)
    json_rows=json.dumps(data)
    kwargs['ti'].xcom_push(key='rows',value=json_rows)
    return "OK"

def get_lat_long(country,city):
    geolocator=Nominatim(user_agent="GeoapiDag")
    location=geolocator.geocode(f'{city},{country}',timeout=None)
    if location:
        return location.latitude,location.longitude

    return None

def transfrom_wikipedia_data(**kwargs):
    data=kwargs['ti'].xcom_pull(key='rows',task_ids='extract_data_from_wikipedia')

    data=json.loads(data)
    stadium_df=pd.DataFrame(data)
    stadium_df['location']=stadium_df.apply(lambda x:get_lat_long(x['country'],x['stadium']),axis=1)
    stadium_df['images']=stadium_df['images'].apply(lambda x: x if x not in ['NO_IMAGE','',None] else NO_IMAGE)
    stadium_df['capacity']=stadium_df['capacity'].astype(int)

    #handle duplicates
    duplicates=stadium_df[stadium_df.duplicated(['location'])]
    duplicates['location'] = duplicates.apply(lambda x: get_lat_long(x['country'], x['city']),axis=1)
    stadium_df.update(duplicates)

    #push to xcom
    kwargs['ti'].xcom_push(key='stadium_df',value=stadium_df.to_json())
    return "OK"

def write_wikipedia_data(**kwargs):
    from datetime import datetime
    data = kwargs['ti'].xcom_pull(key='stadium_df', task_ids='transform_wikipedia_data')
    data = json.loads(data)
    data = pd.DataFrame(data)

    file_name = ('stadium_cleaned_' + str(datetime.now().date())
                 + "_" + str(datetime.now().time()).replace(":", "_") + '.csv')

    # data.to_csv('data/' + file_name, index=False)
    data.to_csv('abfs://footballdataeng@footballdataengsa.dfs.core.windows.net/data/'+ file_name,
                storage_options={
                    'account_key':'<account_key>'
                },index=False)
