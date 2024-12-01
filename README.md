# notams
通过NOTAMS获取并绘制火箭发射落区

已打包好的程序下载链接
蓝奏云：https://wwpj.lanzoul.com/iGxs42grf2xg 密码:hqv3

一、关于NOTAM和火箭发射落区

	随着我国航天技术的不断发展进步，航天发射频率正在不断增加。我们常常能看见一些对某次发射型号、时间以及轨道等信息的预测。除根据目标轨道计算发射窗口、通过内部或公开信息渠道获取发射规划安排等方式，普通人提前获知火箭发射信息的重要方法之一就是分析相关NOTAM中包含的落区信息。
	NOTAM（飞行航行通告，飞行航警）是为通知飞行员相关空域或机场的特别安排、临时规定及运作程序的改变而发出的通告。火箭发射常常有残骸（一级、二级等）掉落，为了保障飞行安全，相关部门会在残骸预计会掉落的位置附近提前划出一个区域，禁止飞机飞入，这片区域就是火箭残骸落区。通过分析落区，我们可以获取包括火箭发射时间地点、大致轨道等信息，甚至能根据落区形状分布分析出火箭型号。
	火箭发射相关的NOTAM常常如下所示：A1690/23 - A TEMPORARY DANGER AREA ESTABLISHED BOUNDED BY: N392852E0955438-N385637E0955854-N390118E0970056-N393335E0965708 BACK TO START. VERTICAL LIMITS:SFC-UNL. SFC - UNL, 06 JUL 03:18 2023 UNTIL 06 JUL 04:45 2023. CREATED: 05 JUL 07:40 2023
	其中，形如“A1690/23”的是航警编号，“N392852E0955438-N385637E0955854-N390118E0970056-N393335E0965708”是四个坐标，这四个坐标点圈出的矩形区域就是残骸落区， “06 JUL 03:18 2023 UNTIL 06 JUL 04:45 2023”是航警生效时间，可以判断发射时间所在区间。国内空域的发射落区航警常以“A TEMPORARY DANGER AREA”开头，在其它国家领空以及一些海域上空航警格式会有所不同，这导致获取文昌的发射落区航警往往会略微麻烦一些。但所有的发射落区航警包含的信息基本一致。

	获取NOTAM的方法请移步小工具的帮助。
 
二、关于这个小工具

	这个小工具原理相当简单，通过爬取NOTAM查询网站，分析并获取与发射相关的航警，将NOTAM内容解析并调用百度地图API将其绘制在地图上，以便更直观方便的进行查询。
	这个小工具的主体部分于2022年年底开发，当时我苦恼于手动在地图上标点的麻烦，同时考虑到我还没有任何开发实用项目的经验，于是就编写了一个输入NOTAM后将其在地图上标出的工具来练手，并在之后将它作为个人辅助分析落区的工具。但是因为对字符串的处理不够完善，数据的存储方式不合理，且需要自己手动去网站上搜索NOTAM，这个工具使用起来相当令人脑淤血。
	于是最近，我将小工具进行了重新开发，优化了操作逻辑和字符串处理、图形绘制代码，在原有功能的基础上增加了自动爬取NOTAM的脚本部分，并将界面优化到能用的程度。
	为了编写方便，我选择了本地服务器+web界面的模式作为这个小工具的基础，小工具主要由flask框架的后端和h5/css+js的前端组成，后端包括一个python爬虫脚本、对发射落区NOTAM的筛选以及初步的字符串处理，前端则以进一步的字符串处理、UI界面和地图、图形的绘制为主。

三、工具使用方法与功能介绍

	解压完成后，运行目录中的main.exe
	如果是未打包的项目文件，则在直接运行main.py即可
	之后弹出的窗口为后端控制台，紧接着会自动打开浏览器进入工具界面，使用过程中不要关闭后端控制台，在后端控制台运行的情况下直接在浏览器访问http://127.0.0.1:5000即可进入工具。

	地图上已将我国现有的四个发射场（酒泉、西昌、太原、文昌）标出，进入工具页面后会自动抓取一次航警信息，并在界面上将未来一段时间的发射落区绘制出来。左上角的区域可以自行选定这些航警的颜色，下方的“移除自动绘制落区”按钮则可以删除这些自动绘制的落区。展开“手动输入航警”栏，可以自行输入并绘制航警。百度地图支持卫星地图显示，因此该工具也可以在卫星地图模式下使用

其它页面
b站专栏：https://www.bilibili.com/opus/1005673245294198789
百度贴吧：https://tieba.baidu.com/p/9298301903