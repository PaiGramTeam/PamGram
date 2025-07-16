from metadata.pool.pool_1 import POOL_1
from metadata.pool.pool_2 import POOL_2
from metadata.pool.pool_11 import POOL_11
from metadata.pool.pool_12 import POOL_12
from metadata.pool.pool_21 import POOL_21
from metadata.pool.pool_22 import POOL_22


def get_pool_by_id(pool_type):
    if pool_type == 1:
        return POOL_1
    elif pool_type == 2:
        return POOL_2
    if pool_type == 11:
        return POOL_11
    if pool_type == 12:
        return POOL_12
    if pool_type == 21:
        return POOL_21
    if pool_type == 22:
        return POOL_22
    return None


def get_avatar_pool():
    """获取角色池"""
    return [POOL_11]
