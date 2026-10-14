import pandas as pd
import pytest
from indicators import rsi

def test_rsi_rising_and_flat():
    assert rsi(pd.Series(range(40),dtype=float),14).iloc[-1]==pytest.approx(100)
    assert rsi(pd.Series([10.]*40),14).iloc[-1]==pytest.approx(50)

def test_rsi_range():
    s=rsi(pd.Series([10,11,10,12,11,13,12,14,13,15,14,16,15,17,16,18,17,19,18,20],dtype=float),14)
    assert s.dropna().between(0,100).all()
