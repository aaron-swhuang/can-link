!#/bin/bash

lsof -ti:8501 | xargs kill -9
