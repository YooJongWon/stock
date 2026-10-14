import pandas as pd
import pytest
from indicators import atr

def test_atr_wilder_seed():
    df=pd.DataFrame({"High":[11,12,13,14],"Low":[9,10,11,12],"Close":[10,11,12,13]})
    values=atr(df,3)
    assert values.iloc[2]==pytest.approx(2.0)
    assert values.iloc[3]==pytest.approx(2.0)
