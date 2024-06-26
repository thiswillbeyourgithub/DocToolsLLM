# bash completion support for -m
# DO NOT EDIT.
# This script is autogenerated by fire/completion.py.

_complete--m()
{
  local cur prev opts lastcommand
  COMPREPLY=()
  prev="${COMP_WORDS[COMP_CWORD-1]}"
  cur="${COMP_WORDS[COMP_CWORD]}"
  lastcommand=$(get_lastcommand)

  opts=""
  GLOBAL_OPTIONS=""


  case "${lastcommand}" in
  
    -m)
      
      opts=" ${GLOBAL_OPTIONS}" 
      opts=$(filter_options $opts)
    ;;
  esac

  COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
  return 0
}

get_lastcommand()
{
  local lastcommand i

  lastcommand=
  for ((i=0; i < ${#COMP_WORDS[@]}; ++i)); do
    if [[ ${COMP_WORDS[i]} != -* ]] && [[ -n ${COMP_WORDS[i]} ]] && [[
      ${COMP_WORDS[i]} != $cur ]]; then
      lastcommand=${COMP_WORDS[i]}
    fi
  done

  echo $lastcommand
}

filter_options()
{
  local opts
  opts=""
  for opt in "$@"
  do
    if ! option_already_entered $opt; then
      opts="$opts $opt"
    fi
  done

  echo $opts
}

option_already_entered()
{
  local opt
  for opt in ${COMP_WORDS[@]:0:$COMP_CWORD}
  do
    if [ $1 == $opt ]; then
      return 0
    fi
  done
  return 1
}

is_prev_global()
{
  local opt
  for opt in $GLOBAL_OPTIONS
  do
    if [ $opt == $prev ]; then
      return 0
    fi
  done
  return 1
}

complete -F _complete--m -m

# bash completion support for __main__.py
# DO NOT EDIT.
# This script is autogenerated by fire/completion.py.

_complete-__main__py()
{
  local cur prev opts lastcommand
  COMPREPLY=()
  prev="${COMP_WORDS[COMP_CWORD-1]}"
  cur="${COMP_WORDS[COMP_CWORD]}"
  lastcommand=$(get_lastcommand)

  opts=""
  GLOBAL_OPTIONS="--llm-verbosity --dollar-limit --debug --embed-kwargs --modelname --task --notification-callback --load-embeds-from --private --top-k --embed-model --DIY-rolling-window-embedding --summary-language --chat-memory --query-condense-question --import-mode --no-llm-cache --file-loader-parallel-backend --query-retrievers --query-eval-check-number --query --query-relevancy --llms-api-bases --filetype --summary-n-recursion --query-eval-modelname --save-embeds-as"


  case "${lastcommand}" in
  
    join)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--iterable ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    center)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--fillchar --width ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    expandtabs)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--tabsize ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    removeprefix)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--prefix ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    removesuffix)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--suffix ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    encode)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--encoding --errors ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    rstrip)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--chars ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    VERSION)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="capitalize casefold center count encode endswith expandtabs find format format-map index isalnum isalpha isascii isdecimal isdigit isidentifier islower isnumeric isprintable isspace istitle isupper join ljust lower lstrip maketrans partition removeprefix removesuffix replace rfind rindex rjust rpartition rsplit rstrip split splitlines startswith strip swapcase title translate upper zfill ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    splitlines)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--keepends ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    split)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--maxsplit --sep ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    lstrip)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--chars ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    partition)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--sep ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    rjust)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--fillchar --width ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    zfill)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--width ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    translate)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--table ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    __main__.py)
      
      opts="VERSION prepare-query-task ${GLOBAL_OPTIONS}" 
      opts=$(filter_options $opts)
    ;;

    ljust)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--fillchar --width ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    prepare-query-task)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--self ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    strip)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--chars ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    replace)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--count --new --old ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    rpartition)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--sep ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;

    rsplit)
      
      if is_prev_global; then
        opts="${GLOBAL_OPTIONS}"
      else
        opts="--maxsplit --sep ${GLOBAL_OPTIONS}"
      fi
      opts=$(filter_options $opts)
    ;;
  esac

  COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
  return 0
}

get_lastcommand()
{
  local lastcommand i

  lastcommand=
  for ((i=0; i < ${#COMP_WORDS[@]}; ++i)); do
    if [[ ${COMP_WORDS[i]} != -* ]] && [[ -n ${COMP_WORDS[i]} ]] && [[
      ${COMP_WORDS[i]} != $cur ]]; then
      lastcommand=${COMP_WORDS[i]}
    fi
  done

  echo $lastcommand
}

filter_options()
{
  local opts
  opts=""
  for opt in "$@"
  do
    if ! option_already_entered $opt; then
      opts="$opts $opt"
    fi
  done

  echo $opts
}

option_already_entered()
{
  local opt
  for opt in ${COMP_WORDS[@]:0:$COMP_CWORD}
  do
    if [ $1 == $opt ]; then
      return 0
    fi
  done
  return 1
}

is_prev_global()
{
  local opt
  for opt in $GLOBAL_OPTIONS
  do
    if [ $opt == $prev ]; then
      return 0
    fi
  done
  return 1
}

complete -F _complete-__main__py __main__.py

