import hashlib
import json
import re
import time
import urllib.parse
from collections import deque

import requests
from openpyxl import Workbook


def clean_excel_text(text):
    """
    过滤非法字符，保留中文、英文、数字、常用标点及 emoji
    """
    allowed_chars = re.compile(
        r'[^'
        r'\u4e00-\u9fff'  # 中文
        r'a-zA-Z0-9'  # 英文数字
        r'\s_,.!?;:，。！？；：“”‘’（）【】《》…—～·'
        r'\U0001F600-\U0001F64F'
        r']+'
    )
    return allowed_chars.sub('', str(text))


def get_mixin_key(raw_wbi_key: str) -> str:
    MIXIN_KEY_ENC_TAB = [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
        27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
        37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
        22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52
    ]
    return ''.join(raw_wbi_key[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def compute_w_rid(params: dict, mixin_key: str) -> str:
    sign_params = {k: str(v) for k, v in params.items() if k != "w_rid"}
    sorted_keys = sorted(sign_params.keys())
    encoded_list = []
    for key in sorted_keys:
        encoded_key = urllib.parse.quote(key, safe='')
        encoded_value = urllib.parse.quote(sign_params[key], safe='')
        encoded_list.append(f"{encoded_key}={encoded_value}")
    query_str = "&".join(encoded_list)
    to_sign = query_str + mixin_key
    return hashlib.md5(to_sign.encode('utf-8')).hexdigest()


class BiliCommentSpider:
    def __init__(self, url_list):
        """
        初始化时传入视频链接列表，后续会转换成 aid 进行爬取
        """
        self.url_list = url_list

        # API接口配置
        self.main_api = "https://api.bilibili.com/x/v2/reply/wbi/main"  # 主评论接口
        self.reply_api = "https://api.bilibili.com/x/v2/reply/reply"  # 子评论接口

        # Cookie 和请求头配置
        self.cookies = {
            # 如有需要，可配置 Cookie
        }
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/"
        }

        self.img_key = "7cd084941338484aae1ad9425b84077c"
        self.sub_key = "4932caff0ff746eab6f01bf08b70ac45"
        self.mixin_key = get_mixin_key(self.img_key + self.sub_key)

        # 固定参数
        self.plat = 1
        self.mode = 3
        self.seek_rpid = ""
        self.web_location = "1315875"

        # 数据存储
        self.output_data = None
        self.counters = None

    def get_base_params(self, oid):
        """构造主评论初始请求参数"""
        return {
            "oid": oid,
            "type": 1,
            "mode": self.mode,
            "pagination_str": '{"offset":""}',
            "plat": self.plat,
            "seek_rpid": self.seek_rpid,
            "web_location": self.web_location,
            "wts": str(int(time.time()))
        }

    def safe_request(self, url, params, max_retries=5):
        for attempt in range(max_retries):
            try:
                params["wts"] = str(int(time.time()))
                params["w_rid"] = compute_w_rid(params, self.mixin_key)
                response = requests.get(
                    url,
                    headers=self.headers,
                    cookies=self.cookies,
                    params=params,
                    timeout=20
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"请求异常: {e} (尝试 {attempt + 1}/{max_retries})")
                time.sleep(3)
        return None

    def fetch_sub_replies(self, oid, root_rpid, ps=10):
        sub_replies = []
        pn = 1
        while True:
            params = {
                "oid": oid,
                "type": 1,
                "root": root_rpid,
                "ps": ps,
                "pn": pn,
                "web_location": "333.788"
            }
            data = self.safe_request(self.reply_api, params)
            if not data or data.get("code") != 0:
                break
            current = data.get("data", {}).get("replies", [])
            if not current:
                break
            sub_replies.extend(current)
            page_info = data.get("data", {}).get("page", {})
            if page_info.get("num", 0) * page_info.get("size", 0) >= page_info.get("count", 0):
                break
            pn += 1
        return sub_replies

    def process_main_comment(self, oid, comment):
        try:
            content = clean_excel_text(comment["content"]["message"])
            # 使用正则表达式删除“回复 汝阳胡歌 : ”这样的字段
            content = re.sub(r'^回复\s+.*?\s*:\s*', '', content)
            self.output_data.append([content, ""])  # text 和 label
            self.counters["valid"] += 1
        except Exception as e:
            print(f"处理主评论出错: {e}")
            self.counters["error"] += 1

        # 处理子评论
        reply_ctrl = comment.get("reply_control", {})
        sub_text = reply_ctrl.get("sub_reply_entry_text", "")
        if sub_text and "共" in sub_text:
            try:
                num = int(re.search(r'\d+', sub_text).group())
            except Exception:
                num = 0
            if num > 0:
                root_rpid = comment.get("rpid")
                sub_list = self.fetch_sub_replies(oid, root_rpid)
                for sub in sub_list:
                    try:
                        sub_content = clean_excel_text(sub["content"]["message"])
                        # 使用正则表达式删除“回复 汝阳胡歌 : ”这样的字段
                        sub_content = re.sub(r'^回复\s+.*?\s*:\s*', '', sub_content)
                        self.output_data.append([sub_content, ""])  # text 和 label
                        self.counters["valid"] += 1
                    except Exception as e:
                        print(f"处理子评论出错: {e}")
                        self.counters["error"] += 1

    def crawl_main(self, oid, title):
        self.output_data = deque()
        self.counters = {"valid": 0, "invalid": 0, "error": 0}

        params = self.get_base_params(oid)
        page_count = 1

        while True:
            print(f"正在抓取 oid={oid} 第 {page_count} 页...")
            data = self.safe_request(self.main_api, params)
            if not data or data.get("code") != 0:
                print(f"oid={oid} 请求失败，状态码: {data.get('code') if data else '无响应'}")
                break

            replies = data.get("data", {}).get("replies", [])
            if not replies:
                print(f"oid={oid} 无更多数据")
                break

            for comment in replies:
                self.process_main_comment(oid, comment)

            print(f"当前有效评论数: {self.counters['valid']}")
            cursor = data.get("data", {}).get("cursor", {})
            if cursor.get("is_end", True):
                print(f"oid={oid} 已到最后一页")
                break
            next_offset = cursor.get("pagination_reply", {}).get("next_offset", "")
            if not next_offset:
                print(f"oid={oid} 无法获取下一页")
                break
            params["pagination_str"] = '{"offset":' + json.dumps(next_offset) + '}'
            page_count += 1

        self.save_to_excel(oid, title)

    def save_to_excel(self, oid, title):
        wb = Workbook()
        ws = wb.active
        ws.title = "B站评论"
        ws.append(["text", "label"])  # 表头
        for text, label in self.output_data:
            try:
                ws.append([text.replace('\n', '↵'), label])
            except Exception as e:
                print(f"写入异常: {e}")
        # 使用标题作为文件名的一部分
        filename = f"../comments/{clean_excel_text(title)}_{oid}_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
        wb.save(filename)
        print(f"数据已保存至: {filename}")

    def get_oid_from_url(self, url):
        """
        从B站视频链接中提取 oid（aid）和标题
        """
        try:
            resp = requests.get(url, headers=self.headers)
            resp.raise_for_status()
            # 提取 aid
            aid_obj = re.compile(r'"aid":(?P<id>\d+),"bvid":')
            match_aid = aid_obj.search(resp.text)
            if not match_aid:
                print(f"未在链接 {url} 中找到 aid")
                return None, None
            oid = match_aid.group('id')
            # 提取标题
            title_obj = re.compile(r'<title data-vue-meta="true">(?P<title>.*?)_哔哩哔哩_bilibili</title>')
            match_title = title_obj.search(resp.text)
            if not match_title:
                print(f"未在链接 {url} 中找到标题")
                return oid, None
            title = match_title.group('title')
            return oid, title
        except requests.exceptions.RequestException as e:
            print(f"请求链接 {url} 失败: {e}")
            return None, None
        except Exception as e:
            print(f"发生错误: {e}")
            return None, None

    def run(self):
        start = time.time()
        for url in self.url_list:
            print(f"\n{'=' * 30} 开始处理视频链接: {url} {'=' * 30}")
            oid, title = self.get_oid_from_url(url)
            if not oid:
                print(f"视频链接 {url} 无法提取到 oid，跳过")
                continue
            print(f"提取到 oid: {oid}")
            print(f"视频标题: {title}")
            self.crawl_main(oid, title)
        print("\n统计报告:")
        print(f"总耗时: {time.time() - start:.2f}秒")


if __name__ == "__main__":
    # 视频链接列表
    url_list = \
        [
        'https://www.bilibili.com/video/BV1srZ3YoEKS/?spm_id_from=333.40138.feed-card.all.click'
        ]

    spider = BiliCommentSpider(url_list)
    spider.run()
