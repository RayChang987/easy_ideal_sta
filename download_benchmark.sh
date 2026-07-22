#!/bin/bash
# source: https://github.com/ABKGroup/ISPD26-Contest
curl -L -o ISPD26_public_Benchmarks.tar.gz https://vlsicad.ucsd.edu/ISPD26-Contest/Benchmarks/ISPD26_public_Benchmarks.tar.gz
mkdir -p ./ISPD26-Contest
tar -xf ISPD26_public_Benchmarks.tar.gz -C ./ISPD26-Contest
rm ISPD26_public_Benchmarks.tar.gz

git clone https://github.com/ABKGroup/ISPD26-Contest.git temp
mv temp/Platform ISPD26-Contest/Platform
rm -rf temp
