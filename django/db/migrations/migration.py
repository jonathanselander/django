from __future__ import unicode_literals


class Migration(object):
    """
    The base class for all migrations.

    Migration files will import this from django.db.migrations.Migration
    and subclass it as a class called Migration. It will have one or more
    of the following attributes:

     - operations: A list of Operation instances, probably from django.db.migrations.operations
     - dependencies: A list of tuples of (app_path, migration_name)
     - run_before: A list of tuples of (app_path, migration_name)
     - replaces: A list of migration_names

    Note that all migrations come out of migrations and into the Loader or
    Graph as instances, having been initialized with their app label and name.
    """

    # Operations to apply during this migration, in order.
    operations = []

    # Other migrations that should be run before this migration.
    # Should be a list of (app, migration_name).
    dependencies = []

    # Other migrations that should be run after this one (i.e. have
    # this migration added to their dependencies). Useful to make third-party
    # apps' migrations run after your AUTH_USER replacement, for example.
    run_before = []

    # Migration names in this app that this migration replaces. If this is
    # non-empty, this migration will only be applied if all these migrations
    # are not applied.
    replaces = []

    # Error class which is raised when a migration is irreversible
    class IrreversibleError(RuntimeError):
        pass

    def __init__(self, name, app_label):
        self.name = name
        self.app_label = app_label
        # Copy dependencies & other attrs as we might mutate them at runtime
        self.operations = list(self.__class__.operations)
        self.dependencies = list(self.__class__.dependencies)
        self.run_before = list(self.__class__.run_before)
        self.replaces = list(self.__class__.replaces)

    def __eq__(self, other):
        if not isinstance(other, Migration):
            return False
        return (self.name == other.name) and (self.app_label == other.app_label)

    def __ne__(self, other):
        return not (self == other)

    def __repr__(self):
        return "<Migration %s.%s>" % (self.app_label, self.name)

    def __str__(self):
        return "%s.%s" % (self.app_label, self.name)

    def __hash__(self):
        return hash("%s.%s" % (self.app_label, self.name))

    def mutate_state(self, project_state):
        """
        Takes a ProjectState and returns a new one with the migration's
        operations applied to it.
        """
        new_state = project_state.clone()
        for operation in self.operations:
            operation.state_forwards(self.app_label, new_state)
        return new_state

    def apply(self, project_state, schema_editor, collect_sql=False):
        """
        Takes a project_state representing all migrations prior to this one
        and a schema_editor for a live database and applies the migration
        in a forwards order.

        Returns the resulting project state for efficient re-use by following
        Migrations.
        """
        for operation in self.operations:
            # If this operation cannot be represented as SQL, place a comment
            # there instead
            if collect_sql and not operation.reduces_to_sql:
                schema_editor.collected_sql.append("--")
                schema_editor.collected_sql.append("-- MIGRATION NOW PERFORMS OPERATION THAT CANNOT BE WRITTEN AS SQL:")
                schema_editor.collected_sql.append("-- %s" % operation.describe())
                schema_editor.collected_sql.append("--")
                continue
            # Get the state after the operation has run
            new_state = project_state.clone()
            operation.state_forwards(self.app_label, new_state)
            # Run the operation
            operation.database_forwards(self.app_label, schema_editor, project_state, new_state)
            # Switch states
            project_state = new_state
        return project_state

    def unapply(self, project_state, schema_editor, collect_sql=False):
        """
        Takes a project_state representing all migrations prior to this one
        and a schema_editor for a live database and applies the migration
        in a reverse order.
        """
        # We need to pre-calculate the stack of project states
        to_run = []
        for operation in self.operations:
            # If this operation cannot be represented as SQL, place a comment
            # there instead
            if collect_sql and not operation.reduces_to_sql:
                schema_editor.collected_sql.append("--")
                schema_editor.collected_sql.append("-- MIGRATION NOW PERFORMS OPERATION THAT CANNOT BE WRITTEN AS SQL:")
                schema_editor.collected_sql.append("-- %s" % operation.describe())
                schema_editor.collected_sql.append("--")
                continue
            # If it's irreversible, error out
            if not operation.reversible:
                raise Migration.IrreversibleError("Operation %s in %s is not reversible" % (operation, self))
            new_state = project_state.clone()
            operation.state_forwards(self.app_label, new_state)
            to_run.append((operation, project_state, new_state))
            project_state = new_state
        # Now run them in reverse
        to_run.reverse()
        for operation, to_state, from_state in to_run:
            operation.database_backwards(self.app_label, schema_editor, from_state, to_state)
        return project_state


def swappable_dependency(value):
    """
    Turns a setting value into a dependency.
    """
    return (value.split(".", 1)[0], "__first__")
