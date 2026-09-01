import matplotlib.font_manager as fm
fonts = [f.name for f in fm.fontManager.ttflist]
cjk = [f for f in fonts if 'CJK' in f or 'Wen' in f or 'Droid' in f or 'Noto' in f]
print(sorted(set(cjk)))
