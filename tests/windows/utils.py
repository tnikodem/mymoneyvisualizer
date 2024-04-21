# -*- coding: utf-8 -*-

import pandas as pd


class CallbackCounter:
    def __init__(self):
        self.counter = 0

    def count(self):
        self.counter += 1


def qt_table_to_dataframe(table):
    dict_df = {}
    for i, col in enumerate(table.columns):
        data = []
        for j in range(table.table_widget.rowCount()):
            data += [table.table_widget.item(j, i).text()]
        dict_df[col] = data
    return pd.DataFrame(dict_df)