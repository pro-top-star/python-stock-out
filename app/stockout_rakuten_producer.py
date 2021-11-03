# -*- coding: utf-8 -*-

import argparse
from datetime import datetime, timedelta
from dataclasses import asdict
from typing import List
import uuid

import const
import logger
from mq import MQ, MQMsgData
import rapi


def _send_msg(send_data: MQMsgData,
              queue_name: str,
              routing_key: str,
              log: logger.Logger):
    try:
        with MQ(**const.MQ_CONNECT,
                queue=queue_name,
                routing_key=routing_key) as queue:
            msg = asdict(send_data)
            queue.send_message(message=msg)
            log.info('Send message queue={queue}, data={data}'.format(queue=queue_name, data=msg))
    except Exception:
        log.exception('Failed to send mq message error')
        raise


def _get_order_item_id_list(log: logger.Logger) -> List[str]:
    end_time = datetime.now()
    start_time = end_time - timedelta(days=const.ORDER_LIST_GET_LAST_DAYS)

    with rapi.RakutenAPI(log=log) as api:
        orders = api.order.search(start_datetime=start_time, end_datetime=end_time)
        order_data_list = []
        if orders:
            order_data_list = api.order.get(order_number_list=orders)

        item_ids = []
        for order_data in order_data_list:
            order_progress = order_data.order_progress
            # 受注ステータス(在庫連動対象)
            # 100: 注文確認待ち
            # 200: 楽天処理中
            # 300: 発送待ち
            # 400: 変更確定待ち
            # 500: 発送済
            # 600: 支払手続き中
            # 700: 支払手続き済
            if order_progress not in [100, 200, 300, 400, 500, 600, 700]:
                # 受注ステータス(在庫連動対象外)
                # 800: キャンセル確定待ち
                # 900: キャンセル確定
                continue

            for order_item in order_data.order_items:
                item_ids.append(order_item.manage_number)

    log.info('Get order list: order_list={order_list}'.format(order_list=item_ids))
    return item_ids


def _producer(log: logger.Logger):
    item_ids = _get_order_item_id_list(log=log)
    if not item_ids:
        return

    send_data = MQMsgData(id=str(uuid.uuid4()),
                          item_ids=item_ids,
                          msg_send_time=datetime.now().isoformat())
    log.info('Send MQ')
    # Yahoo!ショッピング
    _send_msg(send_data=send_data,
              queue_name=const.MQ_YSHOP_QUEUE,
              routing_key=const.MQ_YSHOP_ROUTING_KEY,
              log=log)
    # AuPayマーケット
    _send_msg(send_data=send_data,
              queue_name=const.MQ_AU_QUEUE,
              routing_key=const.MQ_AU_ROUTING_KEY,
              log=log)


def main():
    parser = argparse.ArgumentParser(description='stockout_rakuten_producer')
    parser.add_argument('--task_no',
                        required=True,
                        type=int,
                        help='input process No type integer')

    arg_parser = parser.parse_args()
    log = logger.Logger(task_name='stockout-rakuten-producer',
                        sub_name='main',
                        name_datetime=datetime.now(),
                        task_no=arg_parser.task_no,
                        **const.LOG_SETTING)
    log.info('Start task')
    log.info('Input args task_no={task_no}'.format(task_no=arg_parser.task_no))

    _producer(log=log)
    log.info('End task')


if __name__ == '__main__':
    main()
