# Smart-Shelf Weight Event detection


**Identify product transactions based on changes in shelf weight.**

**Detect** products being removed from or placed on a store shelf.

**Detect** product weight changes on the shelf while filtering and handling measurement noise.

**Detection time resolution: \< 1 millisecond**

**Weight measurement resolution: 1 gram.**

**Data analysis of products traction in the store is included too.**

## Requirements

Install and start Docker Desktop on Windows 11. No separate Python or Python-library installation is required on Windows.

## Run the program 

Start Docker Desktop, then open the project folder and double-click:

```
run\_annotated.bat	
```

The detector analyzes all three CSV files, prints the detected events, and saves plots and clearly labeled text results in the `results` folder. The text files contain the weight change, event time, and meaning of each event.

## Run all tests

Double-click:

```
run\_tests.bat
```

## Modify the software

Edit `weight\_event\_detector\_annotated.py` in this folder with a text editor. After saving changes, run `run\_annotated.bat` again. The image is rebuilt automatically, so the new code is included in the next run.

If you change the detector behavior, run `run\_tests.bat` to check whether the expected results still pass.

## Output files

The `results` folder is created automatically. The detector writes PNG plots and text files containing numerical results. Existing files with the same names are replaced on the next run.

