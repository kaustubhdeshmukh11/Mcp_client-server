import random 
from fastmcp import FastMCP 

mcp=FastMCP(name="Demo seerver")

@mcp.tool
def roll_dice(n : int =1)->list[int]:
    """Roll n 6-sidedd dice and return the result"""
    return [random.randint(1,6) for _ in range(n)]

if __name__ =="__main__":
    mcp.run()

