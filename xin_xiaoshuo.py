import requests
import numpy as np
from bs4 import BeautifulSoup

def resp(url, headers):
    result = requests.get(url, headers=headers)
    return result.text

def titles(response, array, start_index):
    page = BeautifulSoup(response, "html.parser")
    title = page.find_all('div', class_='title')
    for i in range(len(title)):
        array[start_index + i][0] = title[i].get_text(strip=True)

def ratings(response, array, start_index):
    page = BeautifulSoup(response, "html.parser")
    ratings = page.find_all('div', class_='rating')
    for i in range(len(ratings)):
        spans = ratings[i].find_all('span')
        rating_num = spans[1].get_text(strip=True)
        review_count_text = spans[2].get_text(strip=True)
        review_count = review_count_text.strip('()人评价').strip()
        array[start_index + i][1] = rating_num
        array[start_index + i][2] = review_count

def authors(response, array, start_index):
    page = BeautifulSoup(response, "html.parser")
    author = page.find_all("div", class_='abstract')
    for i in range(len(author)):
        author_field = ""
        publisher_field = ""
        year_field = ""

        author_name = author[i].get_text(strip=True)
        fields = author_name.split("出版社:")
        if len(fields) >= 2:
            if '作者:' in fields[0]:
                author_field = fields[0].split('作者:')[-1].strip()
            publisher_year_fields = fields[1].split('出版年:')
            if len(publisher_year_fields) >= 2:
                publisher_field = publisher_year_fields[0].strip()
                year_field = publisher_year_fields[1].strip()
            elif len(publisher_year_fields) == 1:
                publisher_field = publisher_year_fields[0].strip()
        else:
            if '作者:' in fields[0]:
                author_field = fields[0].split('作者:')[-1].strip()

        array[start_index + i][2] = author_field
        array[start_index + i][3] = publisher_field
        array[start_index + i][4] = year_field

if __name__ == '__main__':
    headers = {
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    }
    array = np.zeros((100, 5), dtype=np.object_)
    numbers = 25
    global_index = 0

    for i in range(0, numbers*4, numbers):  # Update to 4 pages
        url = f"https://www.douban.com/doulist/45177507/?start={i}"
        print(url)
        response = resp(url, headers)
        titles(response, array, global_index)
        ratings(response, array, global_index)
        authors(response, array, global_index)
        global_index += len(array[global_index:global_index + numbers])

    print(array)
