import os

def check_notebook(notebook):
    return os.system('runipy {0} --html test.html'.format(notebook))
    

def run():
    all_files = os.listdir()
    notebooks = [f for f in all_files if f.endswith('.ipynb')]
    nb_returns = [(nb, check_notebook(nb)) for nb in notebooks]
    all_good = [nb for nb, r in nb_returns if r == 0]
    all_bad = [nb for nb, r in nb_returns if r != 0]
    print("Following notebooks did not return errors:")
    for notebook in all_good:
        print("    {0}".format(notebook))
    print("--------------------------------------")
    if all_bad:
        print("Following notebooks returned errors:")
        for notebook in all_bad:
            print("    {0}".format(notebook))
    else:
        print("No notebooks returned any errors, you're good to go")

if __name__ == '__main__':
    run()
