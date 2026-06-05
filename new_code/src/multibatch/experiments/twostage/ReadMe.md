## Two stage experimental pipeline 
Within this pipeline, the effectiveness of the soft constraints as a means to reduce network vulnerabilities are measured. 

### Running experiments
To run the full experiment
```
  caffeinate -dims uv run python -m multibatch.experiments.twostage \
    --weights 0 1000 \
    -t 4 --configuration handy \
    --time-paper 600 --time-small 600 --time-medium 600 \
    --time-large 600 --time-xlarge 600 --time-industrylite 600 
    -o src/multibatch/experiments/twostage/results/experiment_main.csv

```