from enum import Enum


class OrderType(str, Enum):
    DINE_IN = "dine_in"
    PICKUP = "pickup"
    DELIVERY = "delivery"
