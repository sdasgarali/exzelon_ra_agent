import os
lines = []
def w(s=chr(10)):
    if s == chr(10):
        lines.append(chr(10))
    else:
        lines.append(s + chr(10))
