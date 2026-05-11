from kiteconnect import KiteConnect

api_key = "35clx8i5b5na7iz9"
api_secret = "bqazggm1htv4zl8mlbejhdoo0lu2no6p"

kite = KiteConnect(api_key=api_key)

data = kite.generate_session("ZvwSd0qe7P0wYNVGPz2ezfxkUv2BlOVm", api_secret=api_secret)
access_token = data["access_token"]
print(access_token)

