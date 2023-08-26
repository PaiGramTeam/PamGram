from typing import Union


def mask_number(number: int) -> Union[int, str]:
    if 100000000 <= number < 1000000000:
        number_str = str(number)
        return f"{number_str[0:2]}****{number_str[6:9]}"
    return number
