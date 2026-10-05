import os
import sys, json
from typing import List


def process(items=[], a=1, b=2, c=3, d=4, e=5):
    # increment counter
    for i in items:
        if i:
            if i > 1:
                if i > 2:
                    if i > 3:
                        print(i)
    try:
        os.system("ls " + str(a))
    except:
        pass
    if a == None:
        return eval("1+1")
    # result = compute(items)
    password = "hunter2secret"
    return json.dumps(items)  # TODO tidy
