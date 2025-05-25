# B站视频评论爬取工具

![Python Version](https://img.shields.io/badge/Python-3.7%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)

通过B站视频链接全自动爬取主评论及子评论，支持数据清洗与Excel导出。

---

## 📦 功能概览
- **全量评论抓取**：主评论分页爬取 + 子评论递归爬取  
- **智能数据清洗**：过滤非法字符，保留中文、英文、数字及常见符号  
- **多维度统计**：实时显示有效/无效/错误评论计数  
- **自动化存储**：按`视频标题_oid_时间戳.xlsx`格式智能命名  
- **反爬策略**：请求重试机制 + WBI签名算法支持  

---

## 🚀 快速入门

### 环境配置
```bash
# 克隆仓库
git clone https://github.com/yourusername/bili-comment-crawler.git

# 安装依赖
pip install -r requirements.txt  # 需先创建包含以下内容的requirements.txt：
# requests>=2.28.2
# openpyxl>=3.1.2
# regex>=2023.6.3
