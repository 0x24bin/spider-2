## telnet_wifi.py

参考： [TPLINKKEY](https://github.com/kbdancer/TPLINKKEY)

- 基于Python3.x多线程
- 支持多种IP列表格式


#### 参数

因作为自启动，参数直接写脚本里面，列表模式直接载入扫描；掩码/范围模式可能数量较多，按组循环载入扫描，每扫描结束同时会删除该组IP，以防中途中断重启脚本重复扫描。

```
###
#   IP文本格式
#   0 - 默认，列表模式，一个IP一行
#   1 - 掩码模式，一组IP一行，192.168.1.1/24
#   2 - 范围模式，一组IP一行，空格分开，192.168.1.1 192.168.1.255
###
IP_TYPE  = 0
TIMEOUT  = 10           # 超时，单位秒
MAX_TASK = 256          # 线程数
IP_FILE  = 'ip.txt'     # IP文本名称，与脚本放同一目录
LOG_FILE = 'log.log'    # 日志文件，缺省在脚本同一目录
```

#### 开机启动

kali下在`/etc/rc.local`加入启动脚本

```
python3 /xxx/telnet_wifi.py
```

## wifi.sql

数据表结构，需要位置信息等字段自行加入

## 附件

14+W条记录密码的TOP100、TOP500、TOP1000，跑WIFI包不错的弱口令字典

- password_top100.txt
- password_top100.txt
- password_top100.txt


> 注：仅供学习交流，使用造成后果与我无关。