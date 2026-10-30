"""客户自助双录页面切换：以新页面状态确认动作结果。"""
import re
import time
import xml.etree.ElementTree as ET


def snapshot(d):
    nodes = []
    for node in ET.fromstring(d.dump_hierarchy()).iter('node'):
        bounds = list(map(int, re.findall(r'-?\d+', node.get('bounds', ''))))
        if len(bounds) == 4 and bounds[2] > bounds[0] and bounds[3] > bounds[1]:
            nodes.append((node.attrib, bounds))
    return nodes


def find(nodes, label):
    return next((n for n in nodes if label in (n[0].get('text'), n[0].get('content-desc'))), None)


def login_page(nodes):
    return find(nodes, '客户登录') and any(n[0].get('class') == 'android.widget.EditText' for n in nodes)


def bottom_navigation(nodes, label):
    """导航必须在屏幕底部同一行；订单卡片的同名字段不能作为候选。"""
    height = max((n[1][3] for n in nodes), default=0)
    row = {}
    for name in ('我的', '自助', '纯录制'):
        candidates = [n for n in nodes if name in (n[0].get('text'), n[0].get('content-desc'))
                      and n[1][1] >= height * 0.85]
        if not candidates:
            return None
        row[name] = max(candidates, key=lambda n: n[1][1])
    centers = [(n[1][1] + n[1][3]) / 2 for n in row.values()]
    if max(centers) - min(centers) > height * 0.05:
        return None
    return row.get(label)


def order_page(nodes):
    return (not login_page(nodes) and not find(nodes, '业务办理完成')
            and not find(nodes, '订单详情') and (
                bool(bottom_navigation(nodes, '自助')) or order_list_header(nodes)
            ))


def order_list_header(nodes, title=None):
    """部分 WebView 层级暂不暴露底部导航，以顶部标题和筛选栏核验列表。"""
    titles = (title,) if title else ('远程双录', '自助双录', '纯录制')
    header = next((n for n in nodes if n[0].get('text') in titles and n[1][1] < 200), None)
    return bool(header and any(find(nodes, label) for label in ('订单状态', '产品类型', '查询日期')))


def tap(d, node):
    _, (left, top, right, bottom) = node
    d.click((left + right) // 2, (top + bottom) // 2)


def self_navigation_selected(d):
    """WebView 无障碍树未更新时，用客户四栏导航的蓝色选中态复核。"""
    screen = d.screenshot().convert('RGB')
    width, height = screen.size
    counts = []
    for index in range(4):
        region = screen.crop((int(width * index / 4), int(height * .94),
                              int(width * (index + 1) / 4), int(height * .99)))
        counts.append(sum(1 for r, g, b in region.getdata()
                          if b > 150 and b > r * 1.4 and g > r * 1.2))
    return counts[1] > 30 and counts[1] > max(counts[0], counts[2], counts[3]) * 2


def transition(d, cycle, action, timeout=30):
    """动作可以重试，但必须由目标页面确认成功。"""
    deadline = time.monotonic() + timeout
    last_click = -10
    while time.monotonic() < deadline:
        try:
            nodes = snapshot(d)
            loading = any('加载中' in n[0].get('text', '') for n in nodes)
            target = None
            if action == 'login':
                if order_page(nodes) and not loading:
                    return
                # 登录已提交，只等待结果，不在加载期间重复提交。
            elif action == 'self':
                if find(nodes, '订单详情'):
                    d.screenshot(f'customer_self_error_navigation_detail_{cycle}.png')
                    raise RuntimeError(f'第{cycle}次 - 切换自助时进入订单详情，停止点击')
                if order_list_header(nodes, '自助双录') and not loading:
                    return
                if order_page(nodes) and not loading:
                    # 层级有时仍保留远程页的完整导航；不能仅在导航缺失时核验屏幕。
                    if self_navigation_selected(d):
                        return
                    target = bottom_navigation(nodes, '自助')
                    if target is None:
                        # 部分 WebView 保留远程标题且不暴露导航，不能仅凭旧标题超时。
                        width, height = d.window_size()
                        target = ({}, [int(width * .25), int(height * .94),
                                       int(width * .5), int(height * .99)])
            elif action == 'return':
                if order_page(nodes) and not loading:
                    return
                if find(nodes, '业务办理完成'):
                    target = find(nodes, '返回')
            elif action == 'logout':
                # 必须先检查登出结果，不能继续点击已消失的确认节点。
                if login_page(nodes):
                    return
                if find(nodes, '确认'):
                    target = find(nodes, '确认')
                elif find(nodes, '退出登录'):
                    target = find(nodes, '退出登录')
                elif order_page(nodes):
                    target = bottom_navigation(nodes, '我的')
            if target and time.monotonic() - last_click >= 2:
                tap(d, target)
                last_click = time.monotonic()
        except Exception as error:
            if not any(s in str(error) for s in ('StaleObjectException', 'UiObjectNotFoundException')):
                raise
        time.sleep(0.3)
    d.screenshot(f'customer_self_error_{action}_transition_{cycle}.png')
    raise RuntimeError(f'第{cycle}次 - {action}页面切换超时，未确认目标页面')
