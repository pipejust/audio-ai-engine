def test_scope():
    should_close_ws = False
    for i in range(2):
        print(f"Loop {i}: should_close_ws is {should_close_ws}")
        if should_close_ws:
            pass
        should_close_ws = True
test_scope()
