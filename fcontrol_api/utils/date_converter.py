from datetime import datetime

FORMAT = '%Y-%m-%d'


def form_to_datetime(date_string: str):
    return datetime.strptime(date_string, FORMAT)


def datetime_to_string(date_obj: datetime):
    return date_obj.strftime(FORMAT)
