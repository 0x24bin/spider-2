#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import asyncio
import aiohttp
import aiomysql
from bs4 import BeautifulSoup

TIMEOUT  = 60
DIR_PATH = os.path.dirname(os.path.realpath(__file__))
BAK_PATH = '{}/bak'.format(DIR_PATH)
MIN_PROXY_SIZE = 350  # 代理数低于时，限制访问频率

logging.basicConfig(
    filename = '{}/freebuf.log'.format(DIR_PATH)
   ,filemode = 'w'
   ,level    = logging.DEBUG
   ,format   = '%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

loop = asyncio.get_event_loop()


class Crawler:
    def __init__(self, max_pid, max_tasks=32):
        self.pool = None
        self.lock = asyncio.Lock()
        self.url       = 'http://www.freebuf.com/?p={}&preview=true'
        self.test_url  = 'http://www.freebuf.com/'      # 测试连接
        self.test_txt  = 'FreeBuf.COM | 关注黑客与极客'   # 你认为返回内容中包含的文本
        self.max_pid   = max_pid + 1
        self.max_tasks = max_tasks + 1
        self.pid_queue = asyncio.Queue()
        self.pxy_queue = asyncio.Queue()
        self.headers   = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:45.0)'}

    
    # 数据库连接池
    async def create_pool(self):
        self.pool = await aiomysql.create_pool(host='127.0.0.1'
                                              ,db='freebuf.com'
                                              ,user='freebuf.com'
                                              ,password='freebuf.com'
                                              ,charset='utf8'
                                              ,unix_socket='/var/run/mysqld/mysqld.sock'
                                              ,loop=loop
                                              ,minsize=1
                                              ,maxsize=20)
    
    # 添加、更新、删除
    async def query(self, sql):
        with (await self.pool) as conn:
            cur = await conn.cursor()
            try:
                await cur.execute(sql)
                await cur.close()
                await conn.commit()
            except:
                logger.error(sql, exc_info=True)

    
    # 查询
    async def find(self, sql):
        with (await self.pool) as conn:
            cur = await conn.cursor(aiomysql.cursors.DictCursor)
            try:
                await cur.execute(sql)
                res = await cur.fetchall()
                return res
            except:
                logger.error(sql, exc_info=True)
                

    # 转义特殊字符
    async def escape_string(self, strs):
        return '' if not strs else aiomysql.escape_string(strs)
    
    
    # 代理抓取网页
    async def get_html(self, url, addr):
        data = {'status':999, 'html':''}
        try:
            conn = aiohttp.ProxyConnector(proxy=addr)
            session = aiohttp.ClientSession(connector=conn, headers=self.headers)
            with aiohttp.Timeout(TIMEOUT):
                async with session.get(url) as resp:
                    data['status'] = resp.status
                    if resp.status == 200:
                        html = await resp.read()
                        data['html'] = html.decode('utf8', 'ignore')
        except:
            pass
        finally:
            session.close()
            
        return data
            
    
    async def worker(self, pid, pxy):
        
        addr = '{}://{}:{}'.format(pxy['type'].lower(), pxy['ip'], pxy['port'])
        # 验证该代理是否能返回真实的数据
        if not pxy['test']:
            data = await self.get_html(self.test_url, addr)
            if data['status']==200 and self.test_txt in data['html']:
                await self.update_proxy('test', 1, pxy)
            else:
                await self.update_proxy('status', 9, pxy)
                return await asyncio.wait([self.pid_queue.put(pid)])
        
        url  = self.url.format(pid)
        data = await self.get_html(url, addr)
        
        status = data['status']
        # 正常返回，排除该pid
        if status in (301, 302, 404):
            return await self.insert_temp(pid, status)
            
        # 一般为代理不能用或400，403，502由代理原因引起的，将文章pid填回任务队列
        if status != 200:
            await asyncio.wait([self.pid_queue.put(pid)])
            return await self.update_proxy('status', 'status+1', pxy)
        
        if not pxy['status']:
            await self.update_proxy('status', 0, pxy)

        html = data['html']
        soup = BeautifulSoup(html, 'lxml')
        arct = soup.find(class_='articlecontent')
        
        # 处理使用200正常返回的404
        if not arct:
            return await self.insert_temp(pid, status)
        
        # 保存副本
        bak_html = '{}/{}.html'.format(BAK_PATH, pid)
        with open(bak_html, 'wt') as f:
            f.write(html)
            
        head     = arct.find(class_='title')
        title    = head.find('h2').get_text().strip()               # 文章标题
        name     = head.find(class_='name').get_text().strip()      # 作者名称
        rtime    = head.find(class_='time').get_text().strip()      # 发布时间
        rmb      = 1 if head.find(title='现金奖励') else 0           
        coin     = 1 if head.find(title='金币奖励') else 0
        identity = 1 if head.find(title='认证作者') else 0
        identity = 2 if not identity and head.find(title='认证厂商') else identity
        tags     = head.find(class_='tags').find_all('a')
        tags     = ','.join([t.get_text().strip() for t in tags])   # 所属分类
        content  = str(arct.find(id='contenttxt')).strip()          # 主题内容，HTLM格式
        
        # 写入数据库
        sql = ('Insert Into posts (pid, title, name, rtime, rmb, coin, identity,'
                    ' tags, content) Values ({pid}, "{title}", "{name}", "{rtime}",'
                        '{rmb}, {coin}, {identity}, "{tags}", "{content}");').format(
                                pid = pid, rmb = rmb, coin = coin, identity = identity
                               ,title   = await self.escape_string(title)
                               ,name    = await self.escape_string(name)
                               ,rtime   = await self.escape_string(rtime)
                               ,tags    = await self.escape_string(tags)
                               ,content = await self.escape_string(content))
        await self.query(sql)
        print('{} {}'.format(rtime, title))
    
    
    # 添加临时表数据
    async def insert_temp(self, pid, status):
        sql = 'Insert Into temp (pid, status) Values ({}, {});'.format(pid, status)
        return await self.query(sql)
        
    
    # 更新代理状态
    async def update_proxy(self, field, value, pxy):
        sql = ('Update proxy Set {}={} where type="{}" And ip="{}" And port={};').format(
                field, value, pxy['type'], pxy['ip'], pxy['port'])
        return await self.query(sql)
    
    
    # 加载代理，如果没有，继续堵塞线程，xx秒检查一次
    async def load_proxy(self):
        sql = 'Select type, ip, port, status, test From proxy Where status<3;'
        res = await self.find(sql)
        logger.info('Loading proxy... size: {}'.format(len(res)))
        
        # 代理较少时，限制访问频率，无代理则堵塞等待
        if len(res) < MIN_PROXY_SIZE:
            await asyncio.sleep(20)
                    
        for r in res:
            await self.pxy_queue.put(r)
            
            
    async def fetch_worker(self):
        while True:
            pid = await self.pid_queue.get()
            
            # 如果代理队列为空，堵塞当前线程，进行加载
            with (await self.lock):
                if self.pxy_queue.empty():
                    await self.load_proxy()
                                        
            pxy = await self.pxy_queue.get()
            
            try:
                await self.worker(pid, pxy)
            finally:
                self.pid_queue.task_done()
                

    async def run(self):
        logger.info('Starting...')
        
        await self.create_pool()
        
        sql = 'Select pid From posts Union Select pid From temp;'
        res = await self.find(sql)
                
        pid_set  = set([r['pid'] for r in res]) if res else set()
        task_set = set([r for r in range(1, self.max_pid)])
        
        # 取集合差为剩余任务pid
        task_set = task_set - pid_set
        if task_set:
            await asyncio.wait([self.pid_queue.put(s) for s in task_set])
            tasks = [asyncio.ensure_future(self.fetch_worker()) for _ in range(self.max_tasks)]
            
            await self.pid_queue.join()

            for task in tasks:
                task.cancel()
                
        self.pool.close()
        await self.pool.wait_closed()
    
        logger.info('Finishing...')
        
    
if __name__ == '__main__':
    if not os.path.exists(BAK_PATH):
        os.makedirs(BAK_PATH)
        
    max_pid   = 105000    # 文章最大pid
    max_tasks = 64        # 同时处理最大任务数
    
    crawler = Crawler(max_pid, max_tasks)
    loop.run_until_complete(crawler.run())
    loop.close()