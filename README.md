--> FireFox <--
https://www.firefox.com/en-US/?utm_campaign=SET_DEFAULT_BROWSER

--> Python <--
Download Python:
https://www.python.org/downloads/


--> MongoDB <--
Download MongoDB Community Server (w/ Compass):
https://www.mongodb.com/try/download/community

Uncheck "Run MongoDB as a Service"

--> Packages <--
Download "ClassLink" folder, then put it in LocalDisk (C:)

Download requirements.txt (from terminal), open terminal then type:

cd C:\ClassLink\ClassLink

pip install -r requirements.txt

or

python -m pip install -r requirements.txt

--> AI Model <--
https://drive.google.com/drive/folders/1Sx73zkx7RcZ3eNioFRbS2pwu8WOp_Tkz?usp=sharing

Put "Local_LLM" folder inside "ClassLink" folder.

--> Instructions <--
Locate MongoDB directory, example: "C:\Program Files\MongoDB\Server\8.2\bin".
Open in terminal (CMD):

cd C:\Program Files\MongoDB\Server\8.2\bin

Type:

mongod --dbpath "C:\ClassLink\ClassLink\data"

Open another CMD window and type:

cd C:\ClassLink

Type:

python classlink.py


Have fun ma'am Joella :)
