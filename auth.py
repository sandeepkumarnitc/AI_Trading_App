from kiteconnect import KiteConnect

api_key = "35clx8i5b5na7iz9"
api_secret = "bqazggm1htv4zl8mlbejhdoo0lu2no6p"

kite = KiteConnect(api_key=api_key)
print("Login URL:", kite.login_url())



