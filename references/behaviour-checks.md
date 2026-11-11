# Behaviour checks: gate 3b

What an application will *do*, read from its document before anyone runs it.

A document can be valid, parseable and create cleanly and still describe an
application that does the wrong thing. The same families of defect recur:

- **steps that do nothing.** A create step with no inputs, a "mark as
  exported" update with no inputs (so the same records are picked up again on
  every run), a Condition step that branches on nothing. Every one of them
  creates without a word.
- **steps that do the wrong thing.** A step named for one table that creates a
  record in a different table, or a step named for deleting something that
  instead creates a new record from the deleted one's values.
- **state nothing sets.** A checkbox that an approval decision is supposed to
  set and no rule, pipeline or button ever does, so no record ever reaches the
  step that reads it.
- **sends that never stop.** A scheduled reminder that searches every record
  still matching, so it goes out for every period ever rather than the one that
  just ended, and a scheduled job that logs a run even when it has nothing to
  post.
- **access nobody restricted.** A default role that can delete an audit log
  or edit the application's settings.
- **an environment written into the app.** A link to one realm's hostname in
  an app that lives on another, and a step that runs as one person's
  connection, which stops working when that person leaves.

Each check below looks for one of those shapes in any QBL document - one the
builder wrote, or an export of something built by hand. Most are warnings: a
shape that is usually a mistake and sometimes a choice, which somebody should
confirm. The three that can only be a mistake are errors.

    BHV001  a pipeline action step that writes nothing                    error
    BHV002  a pipeline Condition step with no condition                   error
    BHV003  a loop with nothing in it, or over a step that is not there   error
    BHV004  a Quickbase hostname written into the app                     warning
    BHV005  a pipeline step that runs as one person's connection          warning
    BHV006  a choice or checkbox that logic reads and nothing sets        warning
    BHV007  a scheduled send that will repeat for the same records        warning
    BHV008  a scheduled pipeline that creates a record even on empty runs warning
    BHV009  a non-admin role can delete or change an audit or log table   warning
    BHV010  a non-admin role can change the application's settings        warning
    BHV011  a table opens on a form with nothing on it                    error
    BHV012  a table leans on formula queries                              warning
    BHV013  a parent's Active flag does not reach its children            warning
    BHV014  a status changes and nothing writes it to the audit table     warning
    BHV015  a pipeline step named for one table writes to another         warning
    BHV016  a pipeline filter uses an operator pipelines do not use        warning
    BHV017  a scheduled email has conditions, which the platform drops    warning
