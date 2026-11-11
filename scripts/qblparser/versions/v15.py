from .v14 import QBLv014Handler


class QBLv015Handler(QBLv014Handler):

    def get_version(self):
        return "0.15"
